"""Indicadores del panel de monitoreo (RF06): lo recibido, lo cargado, lo pendiente de revisar y lo descontado.

Todo se calcula en el momento desde la base. El cruce cuenta solo la ejecución vigente de cada informe (la última),
para que volver a cruzar no duplique montos.
"""
from sqlalchemy import Connection, text

from ...db import transaccion
from ..excepciones import servicio as excepciones

# Ejecución vigente de cada informe cruzado.
_VIGENTES = ("cruce.ejecuciones e WHERE e.id_ejecucion = "
             "(SELECT MAX(x.id_ejecucion) FROM cruce.ejecuciones x WHERE x.id_archivo = e.id_archivo)")


def _entero(valor) -> int:
    return int(valor or 0)


def indicadores(conexion: Connection, meses: int = 6, recientes: int = 8) -> dict:
    with transaccion(conexion):
        estados = {estado: cantidad for estado, cantidad in conexion.execute(
            text("SELECT estado_archivo, COUNT(*) FROM dbo.Archivos_TGR GROUP BY estado_archivo ORDER BY 2 DESC"))}
        casos = conexion.execute(text(
            "SELECT COUNT(*), SUM(CASE WHEN rev_manual_bit = 1 THEN 1 ELSE 0 END), SUM(monto_solicitado) "
            "FROM core.casos_tgr")).one()
        cruce = conexion.execute(text(
            "SELECT COUNT(*), SUM(casos), SUM(clientes), SUM(descontados), SUM(parciales), SUM(no_descontados), "
            f"SUM(en_revision), SUM(monto_solicitado), SUM(monto_descontado) FROM {_VIGENTES}")).one()
        por_mes = conexion.execute(text(
            f"SELECT TOP (:meses) periodo, COUNT(*) AS informes, SUM(casos) AS casos, SUM(monto_solicitado) AS solicitado, "
            f"SUM(monto_descontado) AS descontado FROM {_VIGENTES} GROUP BY periodo ORDER BY periodo DESC"),
            {"meses": meses}).mappings().all()
        ultimos = conexion.execute(text(
            "SELECT TOP (:n) a.id_archivo, a.nombre_archivo, a.estado_archivo, a.fecha_recepcion, a.canal_origen, "
            "a.total_registros, c.descontados + c.parciales AS con_descuento, c.monto_descontado "
            "FROM dbo.Archivos_TGR a OUTER APPLY (SELECT TOP 1 * FROM cruce.ejecuciones x "
            "WHERE x.id_archivo = a.id_archivo ORDER BY x.id_ejecucion DESC) c "
            "ORDER BY a.fecha_recepcion DESC, a.id_archivo DESC"), {"n": recientes}).mappings().all()
        rechazados = conexion.execute(text(
            "SELECT COUNT(*) FROM etl.resultados WHERE resultado = N'Rechazado'")).scalar_one()
    pendientes = excepciones.listar(conexion, tipo=None, estado=None, buscar=None, limite=1,
                                    desplazamiento=0)["pendientes"]
    return {
        "informes": {"total": sum(estados.values()), "por_estado": estados},
        "casos": {"total": _entero(casos[0]), "en_revision": _entero(casos[1]), "monto_solicitado": casos[2] or 0,
                  "rechazados_etl": _entero(rechazados)},
        "excepciones_pendientes": pendientes,
        "cruce": {"informes": _entero(cruce[0]), "casos": _entero(cruce[1]), "clientes": _entero(cruce[2]),
                  "descontados": _entero(cruce[3]), "parciales": _entero(cruce[4]),
                  "no_descontados": _entero(cruce[5]), "en_revision": _entero(cruce[6]),
                  "monto_solicitado": cruce[7] or 0, "monto_descontado": cruce[8] or 0},
        "por_mes": [dict(f) for f in reversed(por_mes)],
        "ultimos_informes": [dict(f) for f in ultimos],
    }
