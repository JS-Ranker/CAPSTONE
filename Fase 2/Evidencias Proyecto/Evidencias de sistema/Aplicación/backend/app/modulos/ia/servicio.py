"""Módulo de IA analítica (RF08, CU08): analiza cada informe después del ETL y gestiona sus insights.

- analizar_informe: anomalías de los casos (deteccion.py) y tendencias de rechazo y calidad (tendencias.py),
  comparando con el historial; guarda el análisis y sus insights (ia.analisis, ia.insights).
- revisar_insight: "Aplicar sugerencia de validación" (crea una regla en ia.reglas que el ETL usa desde el
  siguiente informe) o marcarlo como revisado. Todo queda en la bitácora.
- resumen_dia: hallazgos operativos de un día.
"""
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion
from .deteccion import ALTO, BAJO, MEDIO, detectar, pesos
from .reglas import MONTO_MAXIMO
from .tendencias import Hallazgo, motivo_base, tendencias

log = logging.getLogger(__name__)

ANOMALIA = "Anomalía de caso"
PENDIENTE, APLICADA, REVISADA = "Pendiente", "Aplicada", "Revisada"
APLICAR, MARCAR_REVISADA = "aplicar", "revisar"
NIVELES = (ALTO, MEDIO, BAJO)

# Casos con el informe del que salieron (los cargados por el ETL y los creados al corregir una fila rechazada).
_CASOS = """
SELECT c.id_caso, c.rut_limpio AS rut, c.monto_solicitado AS monto, c.tesoreria, c.fec_ing, c.fecha_oficio,
       c.rol_anio, COALESCE(inf.id_archivo, n.id_archivo) AS id_informe
FROM core.casos_tgr c
OUTER APPLY (SELECT TOP 1 e.id_archivo FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion
             WHERE r.id_caso = c.id_caso AND r.resultado = N'Cargado') inf
OUTER APPLY (SELECT TOP 1 e.id_archivo FROM etl.revisiones v JOIN etl.resultados r ON r.id_resultado = v.id_resultado
             JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion WHERE v.id_caso_nuevo = c.id_caso) n
ORDER BY c.id_caso
"""


class InsightNoEncontrado(Exception):
    pass


class AccionNoPermitida(Exception):
    pass


@dataclass(frozen=True)
class ResultadoAnalisis:
    id_analisis: int
    alertas: dict[str, int]


def _alertas(cantidad: int, nivel: str, con_palabra: bool = True) -> str:
    """'1 alerta alta', '3 alertas medias' (o sin la palabra: '1 alta', '3 medias')."""
    plural = "s" if cantidad != 1 else ""
    adjetivo = {ALTO: "alta", MEDIO: "media", BAJO: "baja"}[nivel] + plural
    return f"{cantidad} alerta{plural} {adjetivo}" if con_palabra else f"{cantidad} {adjetivo}"


def _casos(conexion: Connection) -> list[dict]:
    filas = conexion.execute(text(_CASOS)).mappings().all()
    return [dict(f) | {"monto": float(f["monto"]) if f["monto"] is not None else None} for f in filas]


def _resumen_ejecuciones(conexion: Connection) -> dict[int, dict]:
    """Por informe: filas, rechazadas, casos en revisión manual y motivos de rechazo (última ejecución del ETL)."""
    ejecuciones = conexion.execute(text(
        "SELECT e.id_archivo, e.filas_leidas, e.rechazadas, a.tipo_documento, "
        "(SELECT COUNT(*) FROM etl.resultados r JOIN core.casos_tgr c ON c.id_caso = r.id_caso "
        " WHERE r.id_ejecucion = e.id_ejecucion AND r.resultado = N'Cargado' AND c.rev_manual_bit = 1) AS en_revision "
        "FROM etl.ejecuciones e JOIN dbo.Archivos_TGR a ON a.id_archivo = e.id_archivo "
        "WHERE e.id_ejecucion = "
        "(SELECT MAX(e2.id_ejecucion) FROM etl.ejecuciones e2 WHERE e2.id_archivo = e.id_archivo)"
    )).mappings().all()
    resumen = {e["id_archivo"]: {"filas": e["filas_leidas"], "rechazadas": e["rechazadas"],
                                 "en_revision": e["en_revision"], "tipo_documento": e["tipo_documento"],
                                 "motivos": Counter()} for e in ejecuciones}
    motivos = conexion.execute(text(
        "SELECT e.id_archivo, r.motivo FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
        "WHERE r.resultado = N'Rechazado'"
    )).all()
    for id_archivo, motivo in motivos:
        if id_archivo in resumen:
            resumen[id_archivo]["motivos"][motivo_base(motivo)] += 1
    return resumen


def _insertar_insight(conexion: Connection, id_analisis: int, h: Hallazgo, *, id_caso=None, puntaje=None,
                      regla=None) -> None:
    conexion.execute(text(
        "INSERT INTO ia.insights "
        "(id_analisis, tipo, nivel, titulo, detalle, sugerencia, regla_sugerida, id_caso, puntaje) "
        "VALUES (:analisis, :tipo, :nivel, :titulo, :detalle, :sugerencia, :regla, :caso, :puntaje)"
    ), {"analisis": id_analisis, "tipo": h.tipo, "nivel": h.nivel, "titulo": h.titulo[:200],
        "detalle": h.detalle[:2000],
        "sugerencia": h.sugerencia, "regla": json.dumps(regla) if regla else None, "caso": id_caso,
        "puntaje": round(puntaje, 4) if puntaje is not None else None})


def analizar_informe(conexion: Connection, id_archivo: int) -> ResultadoAnalisis:
    """Analiza un informe ya procesado por el ETL. Si ya tenía análisis, lo reemplaza (los insights ya revisados
    se conservan con su análisis anterior)."""
    with transaccion(conexion):
        casos = _casos(conexion)
        objetivo = [c for c in casos if c["id_informe"] == id_archivo]
        historial = [c for c in casos if c["id_informe"] != id_archivo]
        anomalias, info = detectar(historial, objetivo)

        ejecuciones = _resumen_ejecuciones(conexion)
        actual = ejecuciones.get(id_archivo)
        hallazgos = tendencias(actual, [r for i, r in ejecuciones.items() if i != id_archivo]) if actual else []

        conexion.execute(text(
            "DELETE i FROM ia.insights i JOIN ia.analisis a ON a.id_analisis = i.id_analisis "
            "WHERE a.id_archivo = :id AND i.estado = :pendiente"
        ), {"id": id_archivo, "pendiente": PENDIENTE})  # se recalculan; los ya revisados quedan

        alertas = Counter(a.nivel for a in anomalias) + Counter(h.nivel for h in hallazgos)
        partes = [f"{len(objetivo)} casos analizados con {info['modelo']} (historial de {len(historial)} casos)."]
        partes.append(", ".join(_alertas(alertas[n], n) for n in NIVELES if alertas[n]) + "."
                      if alertas else "Sin alertas.")
        id_analisis = conexion.execute(text(
            "INSERT INTO ia.analisis (id_archivo, modelo, casos_analizados, casos_historial, resumen) "
            "OUTPUT INSERTED.id_analisis VALUES (:id, :modelo, :casos, :historial, :resumen)"
        ), {"id": id_archivo, "modelo": info["modelo"], "casos": len(objetivo), "historial": len(historial),
            "resumen": " ".join(partes)}).scalar_one()

        for a in anomalias:
            principal = a.motivos[0].texto
            detalle = " ".join(m.texto for m in a.motivos)
            sugerencia = None
            if a.regla_sugerida:
                sugerencia = (f"Enviar a revisión manual los montos sobre {pesos(a.regla_sugerida['valor'])} "
                              "(hoy el 99% de los casos está bajo ese monto).")
            titulo = f"Caso #{a.id_caso}: {a.motivos[0].titulo or principal}"
            _insertar_insight(conexion, id_analisis, Hallazgo(ANOMALIA, a.nivel, titulo, detalle, sugerencia),
                              id_caso=a.id_caso, puntaje=a.puntaje, regla=a.regla_sugerida)
        for h in hallazgos:
            _insertar_insight(conexion, id_analisis, h)

        bitacora.registrar(conexion, "Análisis IA", {
            "id_archivo": id_archivo, "id_analisis": id_analisis, "modelo": info["modelo"],
            "casos": len(objetivo), "alertas": dict(alertas),
        })
    return ResultadoAnalisis(id_analisis, dict(alertas))


def analizar_sin_fallar(conexion: Connection, id_archivo: int) -> ResultadoAnalisis | None:
    """Análisis después del ETL: si la IA falla, el informe igual queda procesado y la falla queda en la bitácora."""
    try:
        return analizar_informe(conexion, id_archivo)
    except Exception as error:  # noqa: BLE001 - la IA no debe detener la ingesta
        log.exception("Falló el análisis IA del informe %s", id_archivo)
        try:
            with transaccion(conexion):
                bitacora.registrar(conexion, "Análisis IA fallido",
                                   {"id_archivo": id_archivo, "error": error.__class__.__name__})
        except Exception:  # noqa: BLE001
            log.exception("Tampoco se pudo registrar la falla en la bitácora")
        return None


def listar(conexion: Connection, *, informe: int | None, nivel: str | None, estado: str | None,
           limite: int, desplazamiento: int) -> dict:
    condiciones, parametros = [], {"limite": limite, "desplazamiento": desplazamiento}
    for campo, valor, columna in (("informe", informe, "a.id_archivo"), ("nivel", nivel, "i.nivel"),
                                  ("estado", estado, "i.estado")):
        if valor is not None:
            condiciones.append(f"{columna} = :{campo}")
            parametros[campo] = valor
    donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    desde = "FROM ia.insights i JOIN ia.analisis a ON a.id_analisis = i.id_analisis "
    with transaccion(conexion):
        total = conexion.execute(text(f"SELECT COUNT(*) {desde} {donde}"), parametros).scalar_one()
        por_nivel = dict(conexion.execute(text(
            f"SELECT i.nivel, COUNT(*) {desde} {donde} {'AND' if donde else 'WHERE'} i.estado = :pend GROUP BY i.nivel"
        ), parametros | {"pend": PENDIENTE}).all())
        filas = conexion.execute(text(
            "SELECT i.id_insight, i.tipo, i.nivel, i.titulo, i.detalle, i.sugerencia, i.regla_sugerida, i.id_caso, "
            "i.puntaje, i.estado, i.observacion, i.fecha_revision, a.id_archivo AS id_informe, a.fecha, "
            "ar.nombre_archivo "
            f"{desde} JOIN dbo.Archivos_TGR ar ON ar.id_archivo = a.id_archivo {donde} "
            "ORDER BY CASE i.nivel WHEN N'Alto' THEN 0 WHEN N'Medio' THEN 1 ELSE 2 END, a.fecha DESC, i.id_insight "
            "OFFSET :desplazamiento ROWS FETCH NEXT :limite ROWS ONLY"
        ), parametros).mappings().all()
    return {"total": total, "pendientes": {n: por_nivel.get(n, 0) for n in NIVELES},
            "limite": limite, "desplazamiento": desplazamiento,
            "insights": [dict(f) | {"aplicable": bool(f["regla_sugerida"])} for f in filas]}


def analisis_del_informe(conexion: Connection, id_archivo: int) -> dict | None:
    with transaccion(conexion):
        fila = conexion.execute(text(
            "SELECT TOP 1 id_analisis, fecha, modelo, casos_analizados, casos_historial, resumen FROM ia.analisis "
            "WHERE id_archivo = :id ORDER BY id_analisis DESC"
        ), {"id": id_archivo}).mappings().one_or_none()
    return dict(fila) if fila else None


def revisar_insight(conexion: Connection, id_insight: int, accion: str, observacion: str | None) -> str:
    """CU08 paso 4: aplicar la validación sugerida, o 4a: marcar el insight como revisado."""
    nota = (observacion or "").strip()[:1000] or None
    with transaccion(conexion):
        insight = conexion.execute(text(
            "SELECT id_insight, estado, regla_sugerida, titulo FROM ia.insights WITH (UPDLOCK) WHERE id_insight = :id"
        ), {"id": id_insight}).mappings().one_or_none()
        if insight is None:
            raise InsightNoEncontrado(f"No existe el insight #{id_insight}.")
        if insight["estado"] != PENDIENTE:
            raise AccionNoPermitida(f"El insight ya está {insight['estado'].lower()}.")
        id_usuario = bitacora.id_usuario_sistema(conexion)  # sin inicio de sesión todavía (RF09)
        if accion == APLICAR:
            if not insight["regla_sugerida"]:
                raise AccionNoPermitida("Este insight no trae una validación para aplicar.")
            regla = json.loads(insight["regla_sugerida"])
            if regla.get("tipo") != MONTO_MAXIMO:
                raise AccionNoPermitida("Tipo de validación desconocido.")
            # Una sola regla vigente por tipo: la nueva reemplaza a la anterior.
            conexion.execute(text("UPDATE ia.reglas SET activa = 0 WHERE tipo = :tipo AND activa = 1"),
                             {"tipo": regla["tipo"]})
            conexion.execute(text(
                "INSERT INTO ia.reglas (tipo, valor, descripcion, id_insight) VALUES (:tipo, :valor, :desc, :insight)"
            ), {"tipo": regla["tipo"], "valor": regla["valor"], "insight": id_insight,
                "desc": f"Revisión manual de montos sobre {pesos(regla['valor'])}"})
            estado = APLICADA
        elif accion == MARCAR_REVISADA:
            estado = REVISADA
        else:
            raise AccionNoPermitida(f"Acción desconocida: {accion}.")
        conexion.execute(text(
            "UPDATE ia.insights SET estado = :estado, observacion = :nota, id_usuario = :usuario, "
            "fecha_revision = SYSDATETIME() WHERE id_insight = :id"
        ), {"estado": estado, "nota": nota, "usuario": id_usuario, "id": id_insight})
        bitacora.registrar(conexion, "Revisión de insight IA", {
            "id_insight": id_insight, "estado": estado, "titulo": insight["titulo"], "observacion": nota,
        }, id_usuario)
    return estado


def resumen_dia(conexion: Connection, dia: date) -> dict:
    """Hallazgos operativos del día (RF08): informes, deudores, resultado del ETL, revisión manual y alertas IA."""
    with transaccion(conexion):
        informes = conexion.execute(text(
            "SELECT COUNT(*), COUNT(CASE WHEN estado_archivo IN (N'Error de Extracción', N'Error') THEN 1 END) "
            "FROM dbo.Archivos_TGR WHERE CAST(fecha_recepcion AS DATE) = :dia"
        ), {"dia": dia}).one()
        etl = conexion.execute(text(
            "SELECT COALESCE(SUM(filas_leidas), 0), COALESCE(SUM(cargadas), 0), COALESCE(SUM(rechazadas), 0), "
            "COALESCE(SUM(duplicadas), 0) FROM etl.ejecuciones WHERE CAST(fecha_inicio AS DATE) = :dia"
        ), {"dia": dia}).one()
        motivos = conexion.execute(text(
            "SELECT r.motivo FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
            "WHERE r.resultado = N'Rechazado' AND CAST(e.fecha_inicio AS DATE) = :dia"
        ), {"dia": dia}).scalars().all()
        alertas = dict(conexion.execute(text(
            "SELECT i.nivel, COUNT(*) FROM ia.insights i JOIN ia.analisis a ON a.id_analisis = i.id_analisis "
            "WHERE CAST(a.fecha AS DATE) = :dia GROUP BY i.nivel"
        ), {"dia": dia}).all())
    recibidos, con_error = informes
    leidos, cargados, rechazados, duplicados = (int(v) for v in etl)
    principal = Counter(motivo_base(m) for m in motivos).most_common(1)
    puntos = []
    if not recibidos and not leidos:
        puntos.append("No se recibieron informes este día.")
    else:
        puntos.append(f"Se recibieron {recibidos} informe{'s' if recibidos != 1 else ''}"
                      + (f" ({con_error} con error de extracción)" if con_error else "") + ".")
        if leidos:
            puntos.append(f"Se leyeron {leidos} deudores: {cargados} cargados, {rechazados} rechazados y "
                          f"{duplicados} duplicados ({100 * rechazados / leidos:.0f}% de rechazo).")
        if principal:
            puntos.append(f"El motivo de rechazo más frecuente fue «{principal[0][0]}» ({principal[0][1]}).")
        total_alertas = sum(alertas.values())
        if total_alertas:
            detalle = ", ".join(_alertas(alertas[n], n, con_palabra=False) for n in NIVELES if alertas.get(n))
            puntos.append(f"La IA generó {total_alertas} alerta{'s' if total_alertas != 1 else ''} ({detalle}).")
    return {"fecha": dia, "informes": recibidos, "informes_con_error": con_error, "deudores_leidos": leidos,
            "cargados": cargados, "rechazados": rechazados, "duplicados": duplicados,
            "alertas": {n: alertas.get(n, 0) for n in NIVELES}, "puntos": puntos}
