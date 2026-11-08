"""Guarda lo que la extracción alcanzó a leer de un informe con error, para corregirlo en la Bandeja de Excepciones.

Un informe que no cuadra (por ejemplo, los montos leídos no suman el total declarado) pasa a 'Error de Extracción'
y no llega al ETL; sin esto, el analista tendría que digitar todo de nuevo (etl.extracciones, 11_extraccion_revision.sql).
"""
import json
from dataclasses import dataclass

from sqlalchemy import Connection, text

from .plantilla import ResultadoExtraccion


@dataclass(frozen=True)
class FilaGuardada:
    orden: int
    valores: dict[str, str]
    confianzas: dict[str, float]


@dataclass(frozen=True)
class ExtraccionGuardada:
    lote: str | None
    fecha_documento: str | None
    cantidad_declarada: int | None
    suma_declarada: int | None
    errores: list[str]
    observaciones: list[str]
    filas: list[FilaGuardada]


def guardar_extraccion(conexion: Connection, id_archivo: int, resultado: ResultadoExtraccion) -> None:
    """Reemplaza lo guardado de ese informe por lo último que se extrajo."""
    parametros = {"id": id_archivo}
    conexion.execute(text("DELETE FROM etl.extraccion_filas WHERE id_archivo = :id"), parametros)
    conexion.execute(text("DELETE FROM etl.extracciones WHERE id_archivo = :id"), parametros)
    conexion.execute(text(
        "INSERT INTO etl.extracciones (id_archivo, lote, fecha_documento, cantidad_declarada, suma_declarada, "
        "errores, observaciones) VALUES (:id, :lote, :fecha, :cantidad, :suma, :errores, :observaciones)"
    ), {
        "id": id_archivo, "lote": resultado.lote, "fecha": resultado.fecha_documento,
        "cantidad": resultado.cantidad_declarada, "suma": resultado.suma_declarada,
        "errores": json.dumps(resultado.errores, ensure_ascii=False),
        "observaciones": json.dumps(resultado.observaciones, ensure_ascii=False),
    })
    if resultado.registros:
        conexion.execute(text(
            "INSERT INTO etl.extraccion_filas (id_archivo, orden, valores, confianzas) "
            "VALUES (:id, :orden, :valores, :confianzas)"
        ), [{
            "id": id_archivo, "orden": orden,
            "valores": json.dumps(registro.valores, ensure_ascii=False),
            "confianzas": json.dumps(registro.confianzas),
        } for orden, registro in enumerate(resultado.registros, start=1)])


def cargar_extraccion(conexion: Connection, id_archivo: int) -> ExtraccionGuardada | None:
    cabecera = conexion.execute(text(
        "SELECT lote, fecha_documento, cantidad_declarada, suma_declarada, errores, observaciones "
        "FROM etl.extracciones WHERE id_archivo = :id"
    ), {"id": id_archivo}).one_or_none()
    if cabecera is None:
        return None
    filas = conexion.execute(text(
        "SELECT orden, valores, confianzas FROM etl.extraccion_filas WHERE id_archivo = :id ORDER BY orden"
    ), {"id": id_archivo}).all()
    lote, fecha, cantidad, suma, errores, observaciones = cabecera
    return ExtraccionGuardada(
        lote, fecha, cantidad, suma, json.loads(errores), json.loads(observaciones),
        [FilaGuardada(orden, json.loads(valores), json.loads(confianzas)) for orden, valores, confianzas in filas],
    )
