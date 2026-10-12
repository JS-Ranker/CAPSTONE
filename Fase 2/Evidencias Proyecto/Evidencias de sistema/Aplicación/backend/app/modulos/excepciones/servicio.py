"""Revisión manual de excepciones (CU05, RF05, RN05).

Dos tipos de excepción:
- CASO: un caso de core.casos_tgr marcado para revisión manual (rev_manual_bit = 1). El analista completa
  los datos que faltaron (con las mismas reglas del ETL) y lo regulariza, o lo deja pendiente.
- RECHAZO: una fila que el ETL rechazó (etl.resultados). El analista corrige los datos y la carga como
  caso nuevo (vuelve a pasar por las reglas del ETL), la descarta, o la deja pendiente. Una fila
  descartada se puede reabrir (dejar pendiente): así descartar no es irreversible.

Cada acción agrega una fila a etl.revisiones (historial) y a la bitácora. El estado actual es el de la
última revisión, o "Pendiente" si no tiene ninguna. Los datos tal como llegaron (stg.casos_tgr) no se tocan.
"""
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion
from ..etl.carga import RECHAZADO, casos_existentes, insertar_caso
from ..etl.reglas import COLUMNAS_STG, Caso, Rechazo, corregir_campos, normalizar
from ..recepcion.documentos import DocumentoOriginal, buscar_documento, nombre_en_ruta

CASO, RECHAZO = "caso", "rechazo"
PENDIENTE, RESUELTO, DESCARTADO = "Pendiente", "Resuelto Manual", "Descartado"
REGULARIZAR, CARGAR, DESCARTAR, DEJAR_PENDIENTE = "regularizar", "cargar", "descartar", "pendiente"
ACCIONES = {CASO: (REGULARIZAR, DEJAR_PENDIENTE), RECHAZO: (CARGAR, DESCARTAR, DEJAR_PENDIENTE)}
LARGO_OBSERVACION = 1000

# Fecha local de carga del caso (fecha_carga_utc está en UTC).
_FECHA_LOCAL = "CAST(SWITCHOFFSET(CAST({} AS DATETIMEOFFSET), DATENAME(TZOFFSET, SYSDATETIMEOFFSET())) AS DATETIME2(0))"

# Una fila por excepción, con su estado actual (la última revisión).
_EXCEPCIONES = f"""
WITH ultimas AS (
    SELECT id_caso, id_resultado, estado, observacion,
           ROW_NUMBER() OVER (PARTITION BY id_caso, id_resultado ORDER BY id_revision DESC) AS orden
    FROM etl.revisiones
),
excepciones AS (
    SELECT N'{CASO}' AS tipo, c.id_caso AS id, c.rut_limpio AS rut, c.dv_limpio AS dv, c.nom_cli, c.rol,
           COALESCE(N'Datos vacíos o poco legibles: ' + c.camp_falt, N'Marcado para revisión manual') AS motivo,
           COALESCE(e.id_archivo, n.id_archivo) AS id_informe,
           COALESCE(e.archivo_origen, n.archivo_origen) AS archivo_origen,
           COALESCE(e.fecha_inicio, {_FECHA_LOCAL.format('c.fecha_carga_utc')}) AS fecha,
           COALESCE(u.estado, N'{PENDIENTE}') AS estado, u.observacion
    FROM core.casos_tgr c
    LEFT JOIN ultimas u ON u.id_caso = c.id_caso AND u.orden = 1
    LEFT JOIN etl.resultados r ON r.id_caso = c.id_caso AND r.resultado = N'Cargado'
    LEFT JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion
    -- Un caso creado al corregir una fila rechazada pertenece al informe de esa fila.
    OUTER APPLY (SELECT TOP 1 e2.id_archivo, e2.archivo_origen FROM etl.revisiones v
                 JOIN etl.resultados r2 ON r2.id_resultado = v.id_resultado
                 JOIN etl.ejecuciones e2 ON e2.id_ejecucion = r2.id_ejecucion
                 WHERE v.id_caso_nuevo = c.id_caso) n
    WHERE c.rev_manual_bit = 1 OR u.id_caso IS NOT NULL
    UNION ALL
    SELECT N'{RECHAZO}', r.id_resultado, s.rut, s.dv, s.nom_cli, s.rol, r.motivo,
           e.id_archivo, e.archivo_origen, e.fecha_inicio, COALESCE(u.estado, N'{PENDIENTE}'), u.observacion
    FROM etl.resultados r
    JOIN stg.casos_tgr s ON s.id_stg = r.id_stg
    JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion
    LEFT JOIN ultimas u ON u.id_resultado = r.id_resultado AND u.orden = 1
    WHERE r.resultado = N'{RECHAZADO}'
)
"""


class ExcepcionNoEncontrada(Exception):
    pass


class AccionNoPermitida(Exception):
    """La acción no corresponde al estado actual (por ejemplo, revisar algo ya resuelto)."""


class DatosInvalidos(ValueError):
    """La corrección no cumple las reglas del ETL. `campo` indica cuál, si se sabe."""

    def __init__(self, mensaje: str, campo: str | None = None):
        super().__init__(mensaje)
        self.campo = campo


@dataclass(frozen=True)
class ResultadoRevision:
    estado: str
    id_revision: int
    id_caso_nuevo: int | None = None


def listar(conexion: Connection, *, tipo: str | None, estado: str | None, buscar: str | None,
           limite: int, desplazamiento: int, informe: int | None = None) -> dict:
    condiciones, parametros = [], {"limite": limite, "desplazamiento": desplazamiento}
    if informe is not None:
        condiciones.append("id_informe = :informe")
        parametros["informe"] = informe
    if tipo:
        condiciones.append("tipo = :tipo")
        parametros["tipo"] = tipo
    if estado:
        condiciones.append("estado = :estado")
        parametros["estado"] = estado
    texto = (buscar or "").strip()
    if texto:
        condiciones.append("(rut = :rut OR nom_cli LIKE :patron OR rol LIKE :patron)")
        literal = texto.upper().replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
        parametros |= {"rut": texto.replace(".", "").split("-")[0], "patron": f"%{literal}%"}
    donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    with transaccion(conexion):
        total = conexion.execute(text(f"{_EXCEPCIONES} SELECT COUNT(*) FROM excepciones {donde}"),
                                 parametros).scalar_one()
        # Los pendientes respetan el filtro de informe, pero no los de tipo, estado ni búsqueda.
        del_informe = "AND id_informe = :informe" if informe is not None else ""
        pendientes = dict(conexion.execute(text(
            f"{_EXCEPCIONES} SELECT tipo, COUNT(*) FROM excepciones WHERE estado = :pendiente {del_informe} "
            "GROUP BY tipo"
        ), {"pendiente": PENDIENTE, "informe": informe}).all())
        filas = conexion.execute(text(
            f"{_EXCEPCIONES} SELECT * FROM excepciones {donde} "
            "ORDER BY fecha DESC, tipo, id OFFSET :desplazamiento ROWS FETCH NEXT :limite ROWS ONLY"
        ), parametros).mappings().all()
    return {"total": total, "pendientes": {CASO: pendientes.get(CASO, 0), RECHAZO: pendientes.get(RECHAZO, 0)},
            "limite": limite, "desplazamiento": desplazamiento, "excepciones": [dict(f) for f in filas]}


def pendientes_por_informe(conexion: Connection, informes: list[int]) -> dict[int, int]:
    """Cuántas excepciones pendientes (casos por revisar y filas rechazadas) tiene cada informe recibido."""
    if not informes:
        return {}
    marcadores = ", ".join(f":i{n}" for n in range(len(informes)))
    filas = conexion.execute(text(
        f"{_EXCEPCIONES} SELECT id_informe, COUNT(*) FROM excepciones "
        f"WHERE estado = :pendiente AND id_informe IN ({marcadores}) GROUP BY id_informe"
    ), {"pendiente": PENDIENTE, **{f"i{n}": i for n, i in enumerate(informes)}}).all()
    return dict(filas)


def _historial(conexion: Connection, tipo: str, id_excepcion: int) -> list[dict]:
    columna = "id_caso" if tipo == CASO else "id_resultado"
    filas = conexion.execute(text(
        "SELECT r.id_revision, r.estado, r.observacion, r.cambios, r.id_caso_nuevo, r.fecha, "
        "u.nombre_completo AS usuario "
        f"FROM etl.revisiones r JOIN dbo.Usuarios u ON u.id_usuario = r.id_usuario WHERE r.{columna} = :id "
        "ORDER BY r.id_revision DESC"
    ), {"id": id_excepcion}).mappings().all()
    return [{**fila, "cambios": json.loads(fila["cambios"]) if fila["cambios"] else None} for fila in filas]


def _resumen(conexion: Connection, tipo: str, id_excepcion: int) -> dict:
    fila = conexion.execute(text(f"{_EXCEPCIONES} SELECT * FROM excepciones WHERE tipo = :tipo AND id = :id"),
                            {"tipo": tipo, "id": id_excepcion}).mappings().one_or_none()
    if fila is None:
        raise ExcepcionNoEncontrada(f"No existe la excepción {tipo} #{id_excepcion}.")
    return dict(fila)


def detalle(conexion: Connection, tipo: str, id_excepcion: int) -> dict:
    """Datos del registro, la regla incumplida (motivo), el estado y el historial de revisiones."""
    with transaccion(conexion):
        resumen = _resumen(conexion, tipo, id_excepcion)
        if tipo == CASO:
            datos = conexion.execute(text(
                "SELECT id_caso, rut_limpio, dv_limpio, nom_cli, rol, fec_ing, id_demanda, n_resol, monto_solicitado, "
                "fecha_oficio, tesoreria, est_ret, ent_banco, camp_falt, mult_rol_bit, rev_manual_bit, "
                "id_correo, remit, asunto, ruta_doc FROM core.casos_tgr WHERE id_caso = :id"
            ), {"id": id_excepcion}).mappings().one()
        else:
            datos = conexion.execute(text(
                f"SELECT {', '.join(f's.{c}' for c in COLUMNAS_STG)} FROM etl.resultados r "
                "JOIN stg.casos_tgr s ON s.id_stg = r.id_stg WHERE r.id_resultado = :id"
            ), {"id": id_excepcion}).mappings().one()
        historial = _historial(conexion, tipo, id_excepcion)
        original = buscar_documento(conexion, datos["ruta_doc"], datos["remit"], datos["asunto"])
    documento = {
        "nombre_buscado": nombre_en_ruta(datos["ruta_doc"]),  # para explicar qué se buscó si no aparece
        "id_archivo": original.id_archivo if original else None,
    }
    return {**resumen, "datos": dict(datos), "historial": historial, "documento": documento}


def documento_original(conexion: Connection, tipo: str, id_excepcion: int) -> DocumentoOriginal:
    """PDF o imagen del oficio de la excepción, entre los documentos recibidos ("Ver documento")."""
    with transaccion(conexion):
        _resumen(conexion, tipo, id_excepcion)
        if tipo == CASO:
            consulta = "SELECT ruta_doc, remit, asunto FROM core.casos_tgr WHERE id_caso = :id"
        else:
            consulta = ("SELECT s.ruta_doc, s.remit, s.asunto FROM etl.resultados r "
                        "JOIN stg.casos_tgr s ON s.id_stg = r.id_stg WHERE r.id_resultado = :id")
        ruta_doc, remitente, asunto = conexion.execute(text(consulta), {"id": id_excepcion}).one()
        original = buscar_documento(conexion, ruta_doc, remitente, asunto)
    if original is None:
        nombre = nombre_en_ruta(ruta_doc)
        raise ExcepcionNoEncontrada(
            f"No se encontró {nombre} entre los documentos recibidos." if nombre
            else "La fila no indica el documento original (RUTA DOCUMENTO vacía)."
        )
    return original


def _observacion(observacion: str | None) -> str:
    limpia = (observacion or "").strip()
    if not limpia:
        raise DatosInvalidos("Escriba una observación: queda en el historial.", "observacion")
    if len(limpia) > LARGO_OBSERVACION:
        raise DatosInvalidos(f"La observación admite hasta {LARGO_OBSERVACION} caracteres.", "observacion")
    return limpia


def _estado_actual(conexion: Connection, tipo: str, id_excepcion: int) -> str:
    """Estado vigente, bloqueando la excepción hasta el fin de la transacción (dos analistas a la vez)."""
    columna = "id_caso" if tipo == CASO else "id_resultado"
    estado = conexion.execute(text(
        f"SELECT TOP 1 estado FROM etl.revisiones WITH (UPDLOCK, HOLDLOCK) WHERE {columna} = :id "
        "ORDER BY id_revision DESC"
    ), {"id": id_excepcion}).scalar_one_or_none()
    return estado or PENDIENTE


def _json(valor):
    if isinstance(valor, (date, Decimal)):
        return str(valor)
    return valor


def _registrar(conexion: Connection, tipo: str, id_excepcion: int, estado: str, observacion: str,
               cambios: dict | None, id_caso_nuevo: int | None = None) -> int:
    id_usuario = bitacora.id_usuario_sistema(conexion)  # sin inicio de sesión todavía (RF09)
    id_revision = conexion.execute(text(
        "INSERT INTO etl.revisiones "
        "(id_caso, id_resultado, estado, observacion, cambios, id_caso_nuevo, id_usuario) OUTPUT INSERTED.id_revision "
        "VALUES (:id_caso, :id_resultado, :estado, :observacion, :cambios, :nuevo, :usuario)"
    ), {
        "id_caso": id_excepcion if tipo == CASO else None,
        "id_resultado": id_excepcion if tipo == RECHAZO else None,
        "estado": estado, "observacion": observacion,
        "cambios": json.dumps(cambios, ensure_ascii=False, default=_json) if cambios else None,
        "nuevo": id_caso_nuevo, "usuario": id_usuario,
    }).scalar_one()
    bitacora.registrar(conexion, "Revisión de excepción", {
        "tipo": tipo, "id": id_excepcion, "estado": estado, "observacion": observacion,
        "campos_corregidos": sorted(cambios) if cambios else [], "id_caso_nuevo": id_caso_nuevo,
    }, id_usuario)
    return id_revision


def revisar_caso(conexion: Connection, id_caso: int, accion: str, observacion: str | None,
                 cambios: dict[str, str | None] | None = None) -> ResultadoRevision:
    """Regulariza un caso o lo deja pendiente. En ambos casos se guardan las correcciones enviadas."""
    if accion not in ACCIONES[CASO]:
        raise DatosInvalidos(f"Acción no válida para un caso: {accion}.", "accion")
    nota = _observacion(observacion)
    try:
        valores = corregir_campos(cambios or {})
    except ValueError as error:
        raise DatosInvalidos(str(error), getattr(error, "campo", None)) from error

    with transaccion(conexion):
        _resumen(conexion, CASO, id_caso)  # existe y es una excepción
        if _estado_actual(conexion, CASO, id_caso) == RESUELTO:
            raise AccionNoPermitida("El caso ya fue regularizado.")
        actual = conexion.execute(
            text(f"SELECT {', '.join(valores) or 'id_caso'} FROM core.casos_tgr WHERE id_caso = :id"), {"id": id_caso}
        ).mappings().one()
        diferencias = {campo: {"antes": actual[campo], "despues": valor}
                       for campo, valor in valores.items() if actual[campo] != valor}
        asignaciones = [f"{campo} = :{campo}" for campo in valores if campo in diferencias]
        estado = RESUELTO if accion == REGULARIZAR else PENDIENTE
        if estado == RESUELTO:
            asignaciones.append("rev_manual_bit = 0")
        if asignaciones:
            conexion.execute(
                text(f"UPDATE core.casos_tgr SET {', '.join(asignaciones)}, fecha_actualizacion_utc = SYSUTCDATETIME() "
                     "WHERE id_caso = :id_caso"),
                {**{campo: valores[campo] for campo in diferencias}, "id_caso": id_caso},
            )
        id_revision = _registrar(conexion, CASO, id_caso, estado, nota, diferencias)
    return ResultadoRevision(estado, id_revision)


def revisar_rechazo(conexion: Connection, id_resultado: int, accion: str, observacion: str | None,
                    datos: dict[str, str | None] | None = None) -> ResultadoRevision:
    """Carga una fila rechazada con los datos corregidos, la descarta o la deja pendiente (también para reabrir)."""
    if accion not in ACCIONES[RECHAZO]:
        raise DatosInvalidos(f"Acción no válida para una fila rechazada: {accion}.", "accion")
    nota = _observacion(observacion)
    desconocidos = set(datos or {}) - set(COLUMNAS_STG)
    if desconocidos:
        raise DatosInvalidos("Este campo no existe en el CSV.", sorted(desconocidos)[0])

    with transaccion(conexion):
        _resumen(conexion, RECHAZO, id_resultado)
        estado_actual = _estado_actual(conexion, RECHAZO, id_resultado)
        if estado_actual == RESUELTO:
            raise AccionNoPermitida("La fila ya se cargó como caso.")
        if estado_actual == DESCARTADO and accion != DEJAR_PENDIENTE:
            raise AccionNoPermitida("La fila está descartada: reábrala (dejar pendiente) antes de cargarla.")

        if accion == DESCARTAR:
            return ResultadoRevision(DESCARTADO, _registrar(conexion, RECHAZO, id_resultado, DESCARTADO, nota, None))
        if accion == DEJAR_PENDIENTE:
            return ResultadoRevision(PENDIENTE, _registrar(conexion, RECHAZO, id_resultado, PENDIENTE, nota, None))

        original = dict(conexion.execute(text(
            f"SELECT {', '.join(f's.{c}' for c in COLUMNAS_STG)} FROM etl.resultados r "
            "JOIN stg.casos_tgr s ON s.id_stg = r.id_stg WHERE r.id_resultado = :id"
        ), {"id": id_resultado}).mappings().one())
        corregida = {**original, **(datos or {})}
        normalizada = normalizar(corregida)
        if isinstance(normalizada, Rechazo):
            raise DatosInvalidos(f"Todavía no cumple las reglas del ETL: {normalizada.motivo}")
        assert isinstance(normalizada, Caso)
        existente = casos_existentes(conexion, [normalizada]).get(normalizada.llave)
        if existente is not None:
            raise AccionNoPermitida(f"Ya existe el caso #{existente} con el mismo RUT, rol y fecha de ingreso. "
                                    "Si es el mismo oficio, descarte esta fila.")
        id_caso = insertar_caso(conexion, normalizada)
        diferencias = {campo: {"antes": original[campo], "despues": valor}
                       for campo, valor in (datos or {}).items() if original[campo] != valor}
        id_revision = _registrar(conexion, RECHAZO, id_resultado, RESUELTO, nota, diferencias, id_caso)
    return ResultadoRevision(RESUELTO, id_revision, id_caso)
