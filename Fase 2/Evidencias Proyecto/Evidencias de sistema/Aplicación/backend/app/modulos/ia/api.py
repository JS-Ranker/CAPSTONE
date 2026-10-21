"""Endpoints del módulo de IA analítica (RF08, CU08): insights por informe, revisión y resumen del día.

Pendiente: la plataforma aún no tiene inicio de sesión (CU01, RF09). Cuando exista, revisar un insight debe exigir
el rol Analista o Administrador.
"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ...db import transaccion
from ..recepcion.api import obtener_conexion
from . import servicio

router = APIRouter(prefix="/api/ia", tags=["IA analítica"])


class Revision(BaseModel):
    accion: Literal["aplicar", "revisar"]
    observacion: str | None = Field(None, max_length=1000)


@router.get("/insights")
def listar_insights(
    informe: int | None = Query(None, ge=1, description="Solo los insights de este informe (id_archivo)"),
    nivel: Literal["Alto", "Medio", "Bajo"] | None = None,
    estado: Literal["Pendiente", "Aplicada", "Revisada"] | None = None,
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    conexion: Connection = Depends(obtener_conexion),
):
    """Insights ordenados por nivel (Alto, Medio, Bajo) y del más reciente al más antiguo (CU08 paso 2)."""
    return servicio.listar(conexion, informe=informe, nivel=nivel, estado=estado, limite=limite,
                           desplazamiento=desplazamiento)


@router.post("/insights/{id_insight}/revision")
def revisar(id_insight: int, revision: Revision, conexion: Connection = Depends(obtener_conexion)):
    """Aplicar la validación sugerida (el ETL la usa desde el siguiente informe) o marcar el insight como revisado."""
    try:
        estado = servicio.revisar_insight(conexion, id_insight, revision.accion, revision.observacion)
    except servicio.InsightNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except servicio.AccionNoPermitida as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"id_insight": id_insight, "estado": estado}


@router.get("/informes/{id_archivo}")
def analisis_del_informe(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    analisis = servicio.analisis_del_informe(conexion, id_archivo)
    if analisis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El informe aún no tiene análisis de IA.")
    return analisis


@router.post("/informes/{id_archivo}/analizar", status_code=status.HTTP_201_CREATED)
def analizar(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Vuelve a analizar un informe procesado (por ejemplo, con más historial).

    Los insights ya revisados se conservan.
    """
    with transaccion(conexion):
        procesado = conexion.execute(text("SELECT 1 FROM etl.ejecuciones WHERE id_archivo = :id"),
                                     {"id": id_archivo}).first()
    if procesado is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="El informe no ha pasado por el ETL: no hay casos que analizar.")
    resultado = servicio.analizar_informe(conexion, id_archivo)
    return {"id_analisis": resultado.id_analisis, "alertas": resultado.alertas}


@router.get("/resumen")
def resumen(fecha: date | None = None, conexion: Connection = Depends(obtener_conexion)):
    """Resumen de los hallazgos operativos de un día (por defecto, hoy)."""
    return servicio.resumen_dia(conexion, fecha or date.today())
