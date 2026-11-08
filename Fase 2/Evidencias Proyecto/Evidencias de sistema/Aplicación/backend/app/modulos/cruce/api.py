"""Endpoints del cruce con Banco Genérico (RF04): UTM del mes, cruce de un informe y su resultado.

Pendiente: la plataforma aún no tiene inicio de sesión (CU01, RF09). Cuando exista, fijar la UTM y volver a cruzar
deben exigir el rol Analista o Administrador.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from ..recepcion.api import obtener_conexion
from . import servicio
from .utm_oficial import FUENTE, UtmNoDisponible

router = APIRouter(prefix="/api/cruce", tags=["Cruce con Banco Genérico"])
PERIODO = Path(pattern=r"^20\d{2}-(0[1-9]|1[0-2])$", description="Mes, AAAA-MM")


class ValorUtm(BaseModel):
    valor: Decimal = Field(gt=0, le=10_000_000, decimal_places=2)


@router.get("/utm")
def listar_utm(conexion: Connection = Depends(obtener_conexion)):
    """UTM de los últimos meses, del más reciente al más antiguo."""
    return servicio.listar_utm(conexion)


@router.put("/utm/{periodo}")
def fijar_utm(valor: ValorUtm, periodo: str = PERIODO, conexion: Connection = Depends(obtener_conexion)):
    """Ingresa o corrige la UTM del mes. Los cruces ya hechos conservan la UTM con que se calcularon."""
    servicio.fijar_utm(conexion, periodo, valor.valor)
    return {"periodo": periodo, "valor": valor.valor}


@router.post("/utm/{periodo}/oficial")
def obtener_utm_oficial(periodo: str = PERIODO, conexion: Connection = Depends(obtener_conexion)):
    """Busca la UTM oficial del mes en mindicador.cl (Banco Central / SII) y la guarda."""
    try:
        valor = servicio.obtener_utm_oficial(conexion, periodo)
    except UtmNoDisponible as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"periodo": periodo, "valor": valor, "fuente": FUENTE}


@router.get("/informes")
def listar_cruces(limite: int = Query(20, ge=1, le=100), conexion: Connection = Depends(obtener_conexion)):
    """Los últimos informes cruzados, con el resumen de su cruce vigente."""
    return servicio.listar_cruces(conexion, limite)


@router.post("/informes/{id_archivo}/cruzar", status_code=status.HTTP_201_CREATED)
def cruzar(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Cruza (o vuelve a cruzar) los casos del informe con las cuentas de Banco Genérico."""
    try:
        return servicio.cruzar_informe(conexion, id_archivo)
    except servicio.InformeNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except servicio.CruceNoPosible as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/informes/{id_archivo}")
def cruce_del_informe(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """El cruce vigente del informe: resumen y resultado de cada caso, con el motivo y las cuentas descontadas."""
    cruce = servicio.cruce_del_informe(conexion, id_archivo)
    if cruce is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El informe aún no se ha cruzado.")
    return cruce
