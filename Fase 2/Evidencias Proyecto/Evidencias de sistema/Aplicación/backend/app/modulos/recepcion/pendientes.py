"""Extracción de los documentos no estructurados recibidos (CU02 paso 5, que extiende a CU12).

Los PDF e imágenes se registran como 'Pendiente de Extracción' y se procesan aparte, porque el OCR tarda.
El documento normalizado se escribe junto al original como `<original>.plantilla.csv` (entrada del ETL).
No ejecute dos procesos a la vez: el estado solo se actualiza si el documento sigue pendiente, pero ambos
harían el OCR.
"""
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion
from ..extraccion import ResultadoExtraccion, escribir_plantilla, extraer
from ..extraccion.plantilla import NORMALIZADO
from .registro import PENDIENTE_EXTRACCION


@dataclass(frozen=True)
class DocumentoPendiente:
    id_archivo: int
    nombre_archivo: str
    tipo_documento: str
    ruta_original: str  # relativa al almacén


@dataclass
class ResumenExtraccion:
    normalizados: int = 0
    con_error: int = 0
    omitidos: int = 0  # otro proceso los actualizó antes

    @property
    def procesados(self) -> int:
        return self.normalizados + self.con_error


def ruta_plantilla(original: Path) -> Path:
    """Dónde queda el documento convertido a la plantilla estándar."""
    return original.with_name(original.name + ".plantilla.csv")


def documentos_pendientes(conexion: Connection, limite: int = 10) -> list[DocumentoPendiente]:
    with transaccion(conexion):
        filas = conexion.execute(
            text("SELECT TOP (:limite) id_archivo, nombre_archivo, tipo_documento, ruta_original "
                 "FROM dbo.Archivos_TGR WHERE estado_archivo = :estado ORDER BY fecha_recepcion, id_archivo"),
            {"limite": limite, "estado": PENDIENTE_EXTRACCION},
        ).all()
    return [DocumentoPendiente(*fila) for fila in filas]


def buscar_pendiente(conexion: Connection, id_archivo: int) -> DocumentoPendiente | None:
    with transaccion(conexion):
        fila = conexion.execute(
            text("SELECT id_archivo, nombre_archivo, tipo_documento, ruta_original FROM dbo.Archivos_TGR "
                 "WHERE id_archivo = :id AND estado_archivo = :estado"),
            {"id": id_archivo, "estado": PENDIENTE_EXTRACCION},
        ).one_or_none()
    return DocumentoPendiente(*fila) if fila else None


def extraer_pendiente(conexion: Connection, documento: DocumentoPendiente, almacen: Path) -> str | None:
    """Extrae un documento y actualiza su estado. Devuelve el estado final, o None si ya no estaba pendiente."""
    original = almacen / documento.ruta_original
    try:
        resultado = extraer(original)  # fuera de la transacción: el OCR puede tardar minutos
    except Exception as exc:  # noqa: BLE001 - un documento ilegible no debe detener el lote
        resultado = ResultadoExtraccion(tipo_documento=documento.tipo_documento,
                                        errores=[f"No se pudo leer el documento ({exc.__class__.__name__})."])
    if resultado.estado == NORMALIZADO:
        escribir_plantilla(resultado, ruta_plantilla(original))

    en_revision = sum(registro.requiere_revision for registro in resultado.registros)
    with transaccion(conexion):
        actualizados = conexion.execute(
            text("UPDATE dbo.Archivos_TGR SET estado_archivo = :estado, total_registros = :total, "
                 "confianza_extraccion = :confianza WHERE id_archivo = :id AND estado_archivo = :pendiente"),
            {"estado": resultado.estado, "total": len(resultado.registros), "id": documento.id_archivo,
             "confianza": resultado.confianza_promedio, "pendiente": PENDIENTE_EXTRACCION},
        ).rowcount
        if not actualizados:
            return None
        bitacora.registrar(conexion, "Extracción de documento", {
            "id_archivo": documento.id_archivo, "nombre_archivo": documento.nombre_archivo,
            "estado": resultado.estado, "registros": len(resultado.registros),
            "registros_en_revision": en_revision, "confianza_promedio": resultado.confianza_promedio,
            "errores": resultado.errores, "observaciones": resultado.observaciones,
        })
    return resultado.estado


def procesar_pendientes(conexion: Connection, almacen: Path, limite: int = 10) -> ResumenExtraccion:
    resumen = ResumenExtraccion()
    for documento in documentos_pendientes(conexion, limite):
        estado = extraer_pendiente(conexion, documento, almacen)
        if estado is None:
            resumen.omitidos += 1
        elif estado == NORMALIZADO:
            resumen.normalizados += 1
        else:
            resumen.con_error += 1
    return resumen
