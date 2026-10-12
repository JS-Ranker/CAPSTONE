"""Documento original (el informe de deudores) de un caso o de una fila rechazada.

RUTA DOCUMENTO trae el informe del que salió la fila. Si viene del CSV de Tomás, es una ruta de su equipo,
que cambia de un equipo a otro; lo que se mantiene es el nombre del archivo, el mismo con que llegó adjunto
en el correo y con el que la recepción lo guardó en Archivos_TGR. Por eso se busca por nombre; si hay varios
con el mismo nombre, se prefiere el del mismo remitente y asunto que la fila, y luego el más reciente.
"""
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, text

from .registro import nombre_seguro

TIPOS_MIME = {
    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".csv": "text/csv", ".txt": "text/plain", ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
VISIBLES_EN_NAVEGADOR = {".pdf", ".jpg", ".jpeg", ".png"}  # el resto se descarga


@dataclass(frozen=True)
class DocumentoOriginal:
    id_archivo: int
    nombre_archivo: str
    ruta_original: str  # relativa al almacén de documentos


def nombre_en_ruta(ruta_doc: str | None) -> str | None:
    """'C:\\TGR\\pdf\\informe.pdf' o 'documentos/informe.pdf' -> 'informe.pdf'."""
    if not ruta_doc or not ruta_doc.strip():
        return None
    return nombre_seguro(ruta_doc.strip())


def buscar_documento(conexion: Connection, ruta_doc: str | None, remitente: str | None,
                     asunto: str | None) -> DocumentoOriginal | None:
    nombre = nombre_en_ruta(ruta_doc)
    if nombre is None:
        return None
    fila = conexion.execute(text(
        "SELECT TOP 1 id_archivo, nombre_archivo, ruta_original FROM dbo.Archivos_TGR WHERE nombre_archivo = :nombre "
        "ORDER BY CASE WHEN remitente = :remitente THEN 0 ELSE 1 END, "
        "CASE WHEN asunto_correo = :asunto THEN 0 ELSE 1 END, fecha_recepcion DESC, id_archivo DESC"
    ), {"nombre": nombre, "remitente": (remitente or "").strip().lower(), "asunto": asunto}).one_or_none()
    return DocumentoOriginal(*fila) if fila else None


def ruta_segura(almacen: Path, documento: DocumentoOriginal) -> Path | None:
    """Ruta en disco del documento, solo si está dentro del almacén y existe."""
    raiz = almacen.resolve()
    ruta = (raiz / documento.ruta_original).resolve()
    if not ruta.is_relative_to(raiz) or not ruta.is_file():
        return None
    return ruta
