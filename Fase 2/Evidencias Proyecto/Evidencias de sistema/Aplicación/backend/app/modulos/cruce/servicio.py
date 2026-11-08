"""Cruce de los casos de un informe con el core de Banco Genérico (RF04).

- fijar_utm / valor_utm: la UTM de cada mes, que actualiza el analista.
- cruzar_informe: aplica la regla de descuento (reglas.py) a los casos del informe con las cuentas activas de sus
  RUT y guarda el resultado (cruce.ejecuciones, cruce.resultados, cruce.descuentos). Se puede repetir, por ejemplo
  después de resolver casos en la Bandeja: cada vez queda una ejecución nueva y la vigente es la última.
- cruzar_sin_fallar: el cruce automático después del ETL. Si falta la UTM del mes o algo falla, el informe queda
  procesado igual y queda constancia en la bitácora.
"""
import logging
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion
from . import utm_oficial
from .reglas import DESCONTADO, NO_DESCONTADO, PARCIAL, REVISION, Cuenta, Deuda, Resultado, calcular

log = logging.getLogger(__name__)
_LOTE_CONSULTA = 1000  # SQL Server admite hasta 2100 parámetros por consulta

# Casos del informe: los cargados por su ETL y los creados al corregir una de sus filas rechazadas. Se excluyen los
# que el analista descartó en la Bandeja (la última revisión del caso es "Descartado").
_CASOS_DEL_INFORME = """
SELECT c.id_caso, c.rut_limpio, c.monto_solicitado, c.fecha_oficio, c.rev_manual_bit
FROM core.casos_tgr c
WHERE (EXISTS (SELECT 1 FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion
               WHERE r.id_caso = c.id_caso AND r.resultado = N'Cargado' AND e.id_archivo = :id)
    OR EXISTS (SELECT 1 FROM etl.revisiones v JOIN etl.resultados r ON r.id_resultado = v.id_resultado
               JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion
               WHERE v.id_caso_nuevo = c.id_caso AND e.id_archivo = :id))
  AND ISNULL((SELECT TOP 1 v.estado FROM etl.revisiones v WHERE v.id_caso = c.id_caso
              ORDER BY v.id_revision DESC), N'') <> N'Descartado'
ORDER BY c.id_caso
"""


class InformeNoEncontrado(Exception):
    pass


class CruceNoPosible(Exception):
    """El informe no tiene casos o falta la UTM del mes."""


@dataclass(frozen=True)
class ResumenCruce:
    id_ejecucion: int
    periodo: str
    valor_utm: Decimal
    casos: int
    clientes: int
    descontados: int
    parciales: int
    no_descontados: int
    en_revision: int
    monto_solicitado: Decimal
    monto_descontado: Decimal


def periodo_de(fecha: date | datetime) -> str:
    return f"{fecha:%Y-%m}"


def valor_utm(conexion: Connection, periodo: str) -> Decimal | None:
    with transaccion(conexion):
        return conexion.execute(text("SELECT valor FROM cruce.utm WHERE periodo = :p"), {"p": periodo}).scalar()


def listar_utm(conexion: Connection, limite: int = 24) -> list[dict]:
    with transaccion(conexion):
        filas = conexion.execute(
            text("SELECT TOP (:limite) periodo, valor, fecha FROM cruce.utm ORDER BY periodo DESC"),
            {"limite": limite},
        ).mappings().all()
    return [dict(f) for f in filas]


def fijar_utm(conexion: Connection, periodo: str, valor: Decimal, id_usuario: int | None = None) -> None:
    """Crea o corrige la UTM de un mes. Los cruces ya hechos conservan la UTM con que se calcularon."""
    with transaccion(conexion):
        anterior = conexion.execute(text("SELECT valor FROM cruce.utm WHERE periodo = :p"),
                                    {"p": periodo}).scalar()
        if anterior is None:
            conexion.execute(text("INSERT INTO cruce.utm (periodo, valor, id_usuario) VALUES (:p, :v, :u)"),
                             {"p": periodo, "v": valor, "u": id_usuario})
        else:
            conexion.execute(text("UPDATE cruce.utm SET valor = :v, id_usuario = :u, fecha = SYSDATETIME() "
                                  "WHERE periodo = :p"), {"p": periodo, "v": valor, "u": id_usuario})
        bitacora.registrar(conexion, "UTM actualizada",
                           {"periodo": periodo, "anterior": anterior, "valor": valor}, id_usuario)


def obtener_utm_oficial(conexion: Connection, periodo: str, id_usuario: int | None = None) -> Decimal:
    """Busca la UTM oficial del mes y la guarda (reemplaza la que hubiera). Lanza UtmNoDisponible si no se puede."""
    valor = utm_oficial.consultar(periodo)
    fijar_utm(conexion, periodo, valor, id_usuario)
    with transaccion(conexion):
        bitacora.registrar(conexion, "UTM oficial obtenida",
                           {"periodo": periodo, "valor": valor, "fuente": utm_oficial.FUENTE}, id_usuario)
    return valor


def _cuentas(conexion: Connection, ruts: list[str]) -> list[Cuenta]:
    cuentas = []
    for inicio in range(0, len(ruts), _LOTE_CONSULTA):
        parte = ruts[inicio:inicio + _LOTE_CONSULTA]
        marcadores = ", ".join(f":r{i}" for i in range(len(parte)))
        filas = conexion.execute(
            text(f"SELECT id_cuenta, rut, numero_cuenta, saldo FROM banco.cuentas "
                 f"WHERE estado = N'Activa' AND rut IN ({marcadores})"),
            {f"r{i}": rut for i, rut in enumerate(parte)},
        )
        cuentas += [Cuenta(id_cuenta, rut, numero, saldo) for id_cuenta, rut, numero, saldo in filas]
    return cuentas


def _contar(resultados: list[Resultado], resultado: str) -> int:
    return sum(1 for r in resultados if r.resultado == resultado)


def cruzar_informe(conexion: Connection, id_archivo: int) -> ResumenCruce:
    """Cruza los casos del informe con la UTM del mes en que se recibió. Todo en una transacción."""
    with transaccion(conexion):
        recepcion = conexion.execute(text("SELECT fecha_recepcion FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                                     {"id": id_archivo}).scalar()
        if recepcion is None:
            raise InformeNoEncontrado("Informe no encontrado.")
        periodo = periodo_de(recepcion)
        utm = conexion.execute(text("SELECT valor FROM cruce.utm WHERE periodo = :p"), {"p": periodo}).scalar()
        if utm is None:
            raise CruceNoPosible(f"Falta el valor de la UTM de {periodo}: ingréselo para poder cruzar el informe.")
        filas = conexion.execute(text(_CASOS_DEL_INFORME), {"id": id_archivo}).all()
        if not filas:
            raise CruceNoPosible("El informe no tiene casos cargados que cruzar.")

        deudas = [Deuda(id_caso, rut, monto, fecha_oficio, bool(revision))
                  for id_caso, rut, monto, fecha_oficio, revision in filas]
        resultados = calcular(deudas, _cuentas(conexion, sorted({d.rut for d in deudas})), utm)
        resumen = ResumenCruce(
            id_ejecucion=0, periodo=periodo, valor_utm=utm, casos=len(resultados),
            clientes=sum(1 for r in resultados if r.cliente),
            descontados=_contar(resultados, DESCONTADO), parciales=_contar(resultados, PARCIAL),
            no_descontados=_contar(resultados, NO_DESCONTADO), en_revision=_contar(resultados, REVISION),
            monto_solicitado=sum((r.monto or Decimal(0) for r in resultados), Decimal(0)),
            monto_descontado=sum((r.descontado for r in resultados), Decimal(0)),
        )
        id_ejecucion = conexion.execute(
            text("INSERT INTO cruce.ejecuciones (id_archivo, periodo, valor_utm, casos, clientes, descontados, "
                 "parciales, no_descontados, en_revision, monto_solicitado, monto_descontado) "
                 "OUTPUT INSERTED.id_ejecucion VALUES (:id_archivo, :periodo, :valor_utm, :casos, :clientes, "
                 ":descontados, :parciales, :no_descontados, :en_revision, :monto_solicitado, :monto_descontado)"),
            {"id_archivo": id_archivo, **{k: v for k, v in asdict(resumen).items() if k != "id_ejecucion"}},
        ).scalar_one()
        for r in resultados:
            id_resultado = conexion.execute(
                text("INSERT INTO cruce.resultados (id_ejecucion, id_caso, resultado, cliente, saldo_total, "
                     "monto_solicitado, monto_descontado, monto_pendiente, motivo) OUTPUT INSERTED.id_resultado "
                     "VALUES (:e, :caso, :resultado, :cliente, :saldo, :monto, :descontado, :pendiente, :motivo)"),
                {"e": id_ejecucion, "caso": r.id_caso, "resultado": r.resultado, "cliente": r.cliente,
                 "saldo": r.saldo_total, "monto": r.monto, "descontado": r.descontado, "pendiente": r.pendiente,
                 "motivo": r.motivo},
            ).scalar_one()
            if r.descuentos:
                conexion.execute(
                    text("INSERT INTO cruce.descuentos (id_resultado, id_cuenta, monto) VALUES (:r, :c, :m)"),
                    [{"r": id_resultado, "c": id_cuenta, "m": monto} for id_cuenta, monto in r.descuentos],
                )
            if r.resultado != REVISION:
                # Columna del modelo de Tomás: "SALDO < 0,5 UTM" (nula si no es cliente).
                conexion.execute(
                    text("UPDATE core.casos_tgr SET saldo_menor_05_utm = :v, "
                         "fecha_actualizacion_utc = SYSUTCDATETIME() WHERE id_caso = :id"),
                    {"v": None if r.bajo_media_utm is None else ("SI" if r.bajo_media_utm else "NO"),
                     "id": r.id_caso},
                )
        resumen = replace(resumen, id_ejecucion=id_ejecucion)
        bitacora.registrar(conexion, "Cruce con Banco Genérico",
                           {"id_archivo": id_archivo, **asdict(resumen)})
    return resumen


def _asegurar_utm(conexion: Connection, id_archivo: int) -> None:
    """Obtiene la UTM oficial del mes de recepción del informe si aún no está cargada. Nunca lanza error."""
    try:
        with transaccion(conexion):
            recepcion = conexion.execute(text("SELECT fecha_recepcion FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                                         {"id": id_archivo}).scalar()
        if recepcion is not None and valor_utm(conexion, periodo_de(recepcion)) is None:
            obtener_utm_oficial(conexion, periodo_de(recepcion))
    except Exception as error:  # noqa: BLE001 - sin UTM el cruce queda pendiente, que es el comportamiento previo
        log.info("No se obtuvo la UTM oficial para el informe %s: %s", id_archivo, error)


def cruzar_sin_fallar(conexion: Connection, id_archivo: int) -> ResumenCruce | None:
    """Cruce automático después del ETL: si no se puede, el informe queda procesado y se anota en la bitácora.

    Si falta la UTM del mes, primero intenta obtener la oficial; si no la consigue, el analista la ingresa a mano.
    """
    try:
        _asegurar_utm(conexion, id_archivo)
        return cruzar_informe(conexion, id_archivo)
    except CruceNoPosible as motivo:
        accion, detalle = "Cruce pendiente", str(motivo)
    except Exception as error:  # noqa: BLE001 - el cruce no debe detener la ingesta
        log.exception("Falló el cruce del informe %s", id_archivo)
        accion, detalle = "Cruce fallido", error.__class__.__name__
    try:
        with transaccion(conexion):
            bitacora.registrar(conexion, accion, {"id_archivo": id_archivo, "motivo": detalle})
    except Exception:  # noqa: BLE001
        log.exception("Tampoco se pudo registrar en la bitácora")
    return None


def listar_cruces(conexion: Connection, limite: int = 20) -> list[dict]:
    """El cruce vigente de los últimos informes cruzados, del más reciente al más antiguo."""
    with transaccion(conexion):
        filas = conexion.execute(
            text("SELECT TOP (:limite) e.*, a.nombre_archivo FROM cruce.ejecuciones e "
                 "JOIN dbo.Archivos_TGR a ON a.id_archivo = e.id_archivo "
                 "WHERE e.id_ejecucion = (SELECT MAX(e2.id_ejecucion) FROM cruce.ejecuciones e2 "
                 "                        WHERE e2.id_archivo = e.id_archivo) "
                 "ORDER BY e.id_ejecucion DESC"),
            {"limite": limite},
        ).mappings().all()
    return [dict(f) for f in filas]


def cruce_del_informe(conexion: Connection, id_archivo: int) -> dict | None:
    """El cruce vigente del informe (su última ejecución), con el resultado de cada caso y sus descuentos."""
    with transaccion(conexion):
        ejecucion = conexion.execute(
            text("SELECT TOP 1 * FROM cruce.ejecuciones WHERE id_archivo = :id ORDER BY id_ejecucion DESC"),
            {"id": id_archivo},
        ).mappings().one_or_none()
        if ejecucion is None:
            return None
        casos = conexion.execute(
            text("SELECT r.id_resultado, r.id_caso, c.rut_limpio AS rut, c.dv_limpio AS dv, c.nom_cli AS nombre, "
                 "c.rol, c.id_demanda, c.n_resol, c.fecha_oficio, r.resultado, r.cliente, r.saldo_total, r.monto_solicitado, "
                 "r.monto_descontado, r.monto_pendiente, r.motivo "
                 "FROM cruce.resultados r JOIN core.casos_tgr c ON c.id_caso = r.id_caso "
                 "WHERE r.id_ejecucion = :e ORDER BY c.rut_limpio, c.fecha_oficio, r.id_caso"),
            {"e": ejecucion["id_ejecucion"]},
        ).mappings().all()
        descuentos: dict[int, list[dict]] = {}
        for fila in conexion.execute(
            text("SELECT d.id_resultado, b.numero_cuenta, b.tipo_cuenta, d.monto FROM cruce.descuentos d "
                 "JOIN cruce.resultados r ON r.id_resultado = d.id_resultado "
                 "JOIN banco.cuentas b ON b.id_cuenta = d.id_cuenta "
                 "WHERE r.id_ejecucion = :e ORDER BY d.id_descuento"),
            {"e": ejecucion["id_ejecucion"]},
        ).mappings():
            descuentos.setdefault(fila["id_resultado"], []).append(
                {"cuenta": fila["numero_cuenta"], "tipo": fila["tipo_cuenta"], "monto": fila["monto"]})
    return {
        **dict(ejecucion),
        "resultados": [{**dict(c), "descuentos": descuentos.get(c["id_resultado"], [])} for c in casos],
    }
