"""Extracción de los documentos no estructurados recibidos (CU02 paso 5, que extiende a CU12).

Los PDF e imágenes se registran como 'Pendiente de Extracción' y se procesan aparte, porque el OCR tarda.
El documento normalizado se escribe junto al original como `<original>.plantilla.csv` (entrada del ETL).
No ejecute dos procesos a la vez: el estado solo se actualiza si el documento sigue pendiente, pero ambos
harían el OCR.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion
from ..extraccion import ResultadoExtraccion, escribir_plantilla, extraer
from ..etl.carga import PROCESADO, ErrorFormatoCsv, ejecutar_filas
from ..etl.desde_informe import filas_para_etl
from ..extraccion.plantilla import ERROR_EXTRACCION, NORMALIZADO
from .registro import PENDIENTE_EXTRACCION


_COLUMNAS = "id_archivo, nombre_archivo, tipo_documento, ruta_original, fecha_recepcion, remitente, asunto_correo"


@dataclass(frozen=True)
class DocumentoPendiente:
    id_archivo: int
    nombre_archivo: str
    tipo_documento: str
    ruta_original: str  # relativa al almacén
    fecha_recepcion: datetime
    remitente: str | None
    asunto_correo: str | None


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
            text(f"SELECT TOP (:limite) {_COLUMNAS} FROM dbo.Archivos_TGR "
                 "WHERE estado_archivo = :estado ORDER BY fecha_recepcion, id_archivo"),
            {"limite": limite, "estado": PENDIENTE_EXTRACCION},
        ).all()
    return [DocumentoPendiente(*fila) for fila in filas]


def buscar_pendiente(conexion: Connection, id_archivo: int) -> DocumentoPendiente | None:
    with transaccion(conexion):
        fila = conexion.execute(
            text(f"SELECT {_COLUMNAS} FROM dbo.Archivos_TGR WHERE id_archivo = :id AND estado_archivo = :estado"),
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
        if resultado.estado != NORMALIZADO:
            return resultado.estado  # el documento completo va a revisión manual (CU12 5b)

        # Los deudores pasan al ETL en la misma transacción: el documento queda "Procesado" con sus casos,
        # o no queda nada a medias. Los dudosos se cargan marcados para revisión manual.
        filas = filas_para_etl(resultado, nombre_archivo=documento.nombre_archivo,
                               fecha_recepcion=documento.fecha_recepcion, remitente=documento.remitente,
                               asunto=documento.asunto_correo)
        try:
            with conexion.begin_nested():
                resumen = ejecutar_filas(conexion, filas, documento.nombre_archivo, documento.id_archivo)
        except ErrorFormatoCsv as error:
            _cambiar_estado(conexion, documento.id_archivo, ERROR_EXTRACCION)
            bitacora.registrar(conexion, "Ejecución ETL rechazada", {
                "id_archivo": documento.id_archivo, "archivo": documento.nombre_archivo, "motivo": str(error)})
            return ERROR_EXTRACCION
        _cambiar_estado(conexion, documento.id_archivo, PROCESADO, resumen.filas_leidas)
    return PROCESADO


def _cambiar_estado(conexion: Connection, id_archivo: int, estado: str, total: int | None = None) -> None:
    conexion.execute(
        text("UPDATE dbo.Archivos_TGR SET estado_archivo = :estado, "
             "total_registros = COALESCE(:total, total_registros) WHERE id_archivo = :id"),
        {"estado": estado, "total": total, "id": id_archivo},
    )


def procesar_pendientes(conexion: Connection, almacen: Path, limite: int = 10) -> ResumenExtraccion:
    resumen = ResumenExtraccion()
    for documento in documentos_pendientes(conexion, limite):
        estado = extraer_pendiente(conexion, documento, almacen)
        if estado is None:
            resumen.omitidos += 1
        elif estado in (NORMALIZADO, PROCESADO):
            resumen.normalizados += 1
        else:
            resumen.con_error += 1
    return resumen
