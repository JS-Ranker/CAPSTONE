"""Endpoints de reportes (RF07, RF11): el informe de respuesta a la TGR y los avisos a clientes, en Excel."""
from collections.abc import Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Connection

from ..recepcion.api import obtener_conexion
from . import avisos, informe_tgr
from .panel import indicadores

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])
TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _descarga(generar: Callable[[Connection, int], tuple[bytes, str]], conexion: Connection, id_archivo: int):
    try:
        contenido, nombre = generar(conexion, id_archivo)
    except informe_tgr.InformeNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except informe_tgr.SinCruce as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(contenido, media_type=TIPO_EXCEL,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"})


@router.get("/panel")
def panel(meses: int = Query(6, ge=1, le=24), conexion: Connection = Depends(obtener_conexion)):
    """Indicadores del panel de monitoreo (RF06): informes, casos, excepciones y resultado del cruce."""
    return indicadores(conexion, meses)


@router.get("/informes/{id_archivo}/respuesta-tgr.xlsx")
def respuesta_a_la_tgr(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Excel con el resumen y el detalle de a quiénes se descontó y a quiénes no, y por qué."""
    return _descarga(informe_tgr.generar, conexion, id_archivo)


@router.get("/informes/{id_archivo}/avisos-clientes.xlsx")
def avisos_a_clientes(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Lista de clientes con descuento y el texto del aviso de cada uno. No se envían correos."""
    return _descarga(avisos.generar, conexion, id_archivo)
