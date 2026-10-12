"""Endpoints del ETL de casos TGR (RF02, RF05): procesar un CSV recibido y consultar casos y rechazos.

Pendiente: la plataforma aún no tiene inicio de sesión (CU01, RF09). Cuando exista, procesar un archivo
debe exigir el rol Analista o Administrador.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Connection, text

from ...db import transaccion
from ..recepcion.api import obtener_almacen, obtener_conexion
from .carga import RECHAZADO, ArchivoNoProcesable, ErrorFormatoCsv, procesar_archivo

router = APIRouter(prefix="/api", tags=["ETL y casos TGR"])

# Casos que salieron de un informe: los que cargó el ETL y los que se crearon al corregir una fila rechazada.
_CASOS_DEL_INFORME = (
    "c.id_caso IN (SELECT r.id_caso FROM etl.resultados r JOIN etl.ejecuciones e "
    "ON e.id_ejecucion = r.id_ejecucion WHERE e.id_archivo = :informe AND r.resultado = N'Cargado' "
    "UNION SELECT v.id_caso_nuevo FROM etl.revisiones v JOIN etl.resultados r ON r.id_resultado = v.id_resultado "
    "JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion WHERE e.id_archivo = :informe)"
)
# Informe del que salió cada caso (para mostrarlo y enlazarlo).
_INFORME_DEL_CASO = (
    "OUTER APPLY (SELECT TOP 1 e.id_archivo FROM etl.resultados r JOIN etl.ejecuciones e "
    "ON e.id_ejecucion = r.id_ejecucion WHERE r.id_caso = c.id_caso AND r.resultado = N'Cargado') inf"
)
# Última revisión manual de cada fila rechazada (etl.revisiones, 07_revisiones.sql).
_ULTIMA_REVISION = (
    "OUTER APPLY (SELECT TOP 1 v.estado, v.id_caso_nuevo FROM etl.revisiones v "
    "WHERE v.id_resultado = r.id_resultado ORDER BY v.id_revision DESC) u"
)
_COLUMNAS_EJECUCION = (
    "id_ejecucion, id_archivo, archivo_origen, fecha_inicio, filas_leidas, cargadas, rechazadas, duplicadas"
)


def _resumen(conexion: Connection, id_ejecucion: int) -> dict:
    return dict(conexion.execute(
        text(f"SELECT {_COLUMNAS_EJECUCION} FROM etl.ejecuciones WHERE id_ejecucion = :id"), {"id": id_ejecucion}
    ).mappings().one())


@router.post("/etl/archivos/{id_archivo}", status_code=status.HTTP_201_CREATED)
def procesar(
    id_archivo: int,
    conexion: Connection = Depends(obtener_conexion),
    almacen: Path = Depends(obtener_almacen),
):
    """Pasa por el ETL un CSV TGR ya recibido (correo, SFTP o web). Responde el resumen de la ejecución."""
    try:
        resumen = procesar_archivo(conexion, id_archivo, almacen)
    except ArchivoNoProcesable as exc:
        codigo = status.HTTP_404_NOT_FOUND if exc.no_encontrado else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=codigo, detail=str(exc)) from exc
    except ErrorFormatoCsv as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"El CSV no tiene el formato TGR: {exc}") from exc
    with transaccion(conexion):
        return _resumen(conexion, resumen.id_ejecucion)


@router.get("/etl/archivos/{id_archivo}")
def ejecucion_de_archivo(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Resultado del ETL para un documento recibido (404 si aún no se procesa)."""
    with transaccion(conexion):
        fila = conexion.execute(
            text(f"SELECT TOP 1 {_COLUMNAS_EJECUCION} FROM etl.ejecuciones "
                 "WHERE id_archivo = :id ORDER BY id_ejecucion DESC"),
            {"id": id_archivo},
        ).mappings().one_or_none()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El archivo no ha pasado por el ETL.")
    return dict(fila)


@router.get("/casos")
def listar_casos(
    buscar: str | None = Query(None, max_length=100, description="RUT (sin puntos ni DV), nombre o rol"),
    revision: bool = Query(False, description="Solo los casos marcados para revisión manual"),
    informe: int | None = Query(None, ge=1, description="Solo los casos de este informe (id_archivo)"),
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    conexion: Connection = Depends(obtener_conexion),
):
    """Casos de core.casos_tgr, del ingreso más reciente al más antiguo."""
    condiciones, parametros = [], {"limite": limite, "desplazamiento": desplazamiento}
    texto = (buscar or "").strip()
    if texto:
        rut = texto.replace(".", "").split("-")[0]
        condiciones.append("(rut_limpio = :rut OR nom_cli LIKE :patron OR rol LIKE :patron)")
        literal = texto.upper().replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")  # comodines de LIKE
        parametros |= {"rut": rut, "patron": f"%{literal}%"}
    if revision:
        condiciones.append("rev_manual_bit = 1")
    if informe is not None:
        condiciones.append(_CASOS_DEL_INFORME)
        parametros["informe"] = informe
    donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    with transaccion(conexion):
        total, en_revision = conexion.execute(text(
            f"SELECT COUNT(*), COUNT(CASE WHEN rev_manual_bit = 1 THEN 1 END) FROM core.casos_tgr c {donde}"
        ), parametros).one()
        casos = conexion.execute(text(
            "SELECT c.id_caso, rut_limpio, dv_limpio, nom_cli, rol, tesoreria, monto_solicitado, est_ret, "
            "fec_ing, fecha_oficio, mult_rol_bit, rev_manual_bit, camp_falt, inf.id_archivo AS id_informe "
            f"FROM core.casos_tgr c {_INFORME_DEL_CASO} {donde} ORDER BY fec_ing DESC, c.id_caso DESC "
            "OFFSET :desplazamiento ROWS FETCH NEXT :limite ROWS ONLY"
        ), parametros).mappings().all()
    return {"total": total, "en_revision": en_revision, "limite": limite, "desplazamiento": desplazamiento,
            "casos": [dict(caso) for caso in casos]}


@router.get("/etl/rechazados")
def listar_rechazados(
    informe: int | None = Query(None, ge=1, description="Solo las filas de este informe (id_archivo)"),
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    conexion: Connection = Depends(obtener_conexion),
):
    """Filas que el ETL rechazó, con su motivo, los datos tal como llegaron y el estado de su revisión manual.

    estado_revision: Pendiente (nadie la ha resuelto), Resuelto Manual (se corrigió y se cargó como el caso
    id_caso_nuevo) o Descartado. Se resuelven en la Bandeja de Excepciones.
    """
    with transaccion(conexion):
        filtro = "AND e.id_archivo = :informe" if informe is not None else ""
        parametros = {"rechazado": RECHAZADO, "informe": informe, "limite": limite, "desplazamiento": desplazamiento}
        total, pendientes = conexion.execute(text(
            "SELECT COUNT(*), COUNT(CASE WHEN u.estado IS NULL OR u.estado = 'Pendiente' THEN 1 END) "
            "FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
            f"{_ULTIMA_REVISION} WHERE r.resultado = :rechazado {filtro}"
        ), parametros).one()
        filas = conexion.execute(text(
            "SELECT r.id_resultado, r.motivo, e.id_ejecucion, e.id_archivo, e.archivo_origen, e.fecha_inicio, "
            "s.rut, s.dv, s.nom_cli, s.rol, s.fec_ing, "
            "COALESCE(u.estado, N'Pendiente') AS estado_revision, u.id_caso_nuevo "
            "FROM etl.resultados r "
            "JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
            "JOIN stg.casos_tgr s ON s.id_stg = r.id_stg "
            f"{_ULTIMA_REVISION} "
            f"WHERE r.resultado = :rechazado {filtro} "
            "ORDER BY e.fecha_inicio DESC, r.id_resultado "
            "OFFSET :desplazamiento ROWS FETCH NEXT :limite ROWS ONLY"
        ), parametros).mappings().all()
    return {"total": total, "pendientes": pendientes, "limite": limite, "desplazamiento": desplazamiento,
            "rechazados": [dict(f) for f in filas]}
