"""Endpoints de la Bandeja de Excepciones (CU05, RF05).

Pendiente: la plataforma aún no tiene inicio de sesión (CU01, RF09). Cuando exista, revisar debe exigir el
rol Analista o Administrador, y la revisión debe quedar a nombre del usuario (hoy, el usuario técnico).
"""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from ..recepcion.api import obtener_almacen, obtener_conexion
from ..recepcion.documentos import TIPOS_MIME, VISIBLES_EN_NAVEGADOR, ruta_segura
from . import servicio
from .servicio import CASO

router = APIRouter(prefix="/api/excepciones", tags=["Bandeja de Excepciones"])

Tipo = Literal["caso", "rechazo"]


class Revision(BaseModel):
    accion: str = Field(..., max_length=20, description="caso: regularizar | pendiente; "
                                                        "rechazo: cargar | descartar | pendiente")
    observacion: str = Field(..., max_length=servicio.LARGO_OBSERVACION)
    # caso: campos corregibles de core.casos_tgr; rechazo: columnas del CSV (nombres de stg.casos_tgr)
    datos: dict[str, str | None] = Field(default_factory=dict, max_length=25)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, servicio.ExcepcionNoEncontrada):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, servicio.AccionNoPermitida):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    campo = getattr(exc, "campo", None)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                         detail={"mensaje": str(exc), "campo": campo})


@router.get("")
def listar(
    tipo: Tipo | None = None,
    estado: Literal["Pendiente", "Resuelto Manual", "Descartado"] | None = None,
    buscar: str | None = Query(None, max_length=100, description="RUT, nombre o rol"),
    informe: int | None = Query(None, ge=1, description="N° del informe recibido (id_archivo)"),
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    conexion: Connection = Depends(obtener_conexion),
):
    """Excepciones con su estado actual, de la más reciente a la más antigua."""
    return servicio.listar(conexion, tipo=tipo, estado=estado, buscar=buscar, limite=limite,
                           desplazamiento=desplazamiento, informe=informe)


@router.get("/{tipo}/{id_excepcion}")
def detalle(tipo: Tipo, id_excepcion: int, conexion: Connection = Depends(obtener_conexion)):
    """Datos del registro, regla incumplida e historial de revisiones ("Revisar detalle")."""
    try:
        return servicio.detalle(conexion, tipo, id_excepcion)
    except servicio.ExcepcionNoEncontrada as exc:
        raise _error(exc) from exc


@router.get("/{tipo}/{id_excepcion}/documento")
def ver_documento(
    tipo: Tipo,
    id_excepcion: int,
    conexion: Connection = Depends(obtener_conexion),
    almacen: Path = Depends(obtener_almacen),
):
    """PDF o imagen original del oficio, para revisarlo junto al formulario ("Ver documento")."""
    try:
        original = servicio.documento_original(conexion, tipo, id_excepcion)
    except servicio.ExcepcionNoEncontrada as exc:
        raise _error(exc) from exc
    ruta = ruta_segura(almacen, original)
    if ruta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"{original.nombre_archivo} está registrado pero no se encuentra en el almacén.")
    extension = ruta.suffix.lower()
    return FileResponse(ruta, media_type=TIPOS_MIME.get(extension, "application/octet-stream"),
                        filename=original.nombre_archivo,
                        content_disposition_type="inline" if extension in VISIBLES_EN_NAVEGADOR else "attachment")


@router.post("/{tipo}/{id_excepcion}/revisiones", status_code=status.HTTP_201_CREATED)
def revisar(tipo: Tipo, id_excepcion: int, revision: Revision, conexion: Connection = Depends(obtener_conexion)):
    """Registra una revisión: regularizar o dejar pendiente un caso; cargar, descartar o dejar pendiente un rechazo."""
    funcion = servicio.revisar_caso if tipo == CASO else servicio.revisar_rechazo
    try:
        resultado = funcion(conexion, id_excepcion, revision.accion, revision.observacion, revision.datos)
    except (servicio.ExcepcionNoEncontrada, servicio.AccionNoPermitida, servicio.DatosInvalidos) as exc:
        raise _error(exc) from exc
    return {"estado": resultado.estado, "id_revision": resultado.id_revision, "id_caso_nuevo": resultado.id_caso_nuevo}
