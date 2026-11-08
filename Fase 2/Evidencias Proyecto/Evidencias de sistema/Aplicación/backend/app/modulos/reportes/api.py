"""Endpoints de reportes (RF07, RF11): el informe de respuesta a la TGR en Excel."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Connection

from ..recepcion.api import obtener_conexion
from . import informe_tgr

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])
TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/informes/{id_archivo}/respuesta-tgr.xlsx")
def respuesta_a_la_tgr(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Excel con el resumen y el detalle de a quiénes se descontó y a quiénes no, y por qué."""
    try:
        contenido, nombre = informe_tgr.generar(conexion, id_archivo)
    except informe_tgr.InformeNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except informe_tgr.SinCruce as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(contenido, media_type=TIPO_EXCEL,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"})
