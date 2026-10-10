"""Extracción y normalización de PDF, escaneos y fotografías a la plantilla estándar (tablas de PDF y OCR local con Tesseract), con nivel de confianza por registro.

Requerimientos: RF12, RN05
Responsable: Héctor Sanhueza

Uso:
    resultado = extraer(Path("nomina.pdf"))
    resultado.estado                # 'Normalizado' o 'Error de Extracción'
    resultado.registros[0].requiere_revision
    escribir_plantilla(resultado, Path("nomina_normalizada.csv"))
"""
from pathlib import Path

from .foto import extraer_foto
from .ocr import extraer_escaneado
from .pdf_texto import extraer_pdf_texto, tiene_texto
from .plantilla import COLUMNAS_PLANTILLA, ResultadoExtraccion, escribir_plantilla

__all__ = ["COLUMNAS_PLANTILLA", "FormatoNoSoportado", "ResultadoExtraccion", "escribir_plantilla", "extraer"]

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png"}


class FormatoNoSoportado(Exception):
    """El documento no es un formato no estructurado que este módulo pueda convertir."""


def extraer(ruta: Path) -> ResultadoExtraccion:
    """Convierte un PDF o una imagen de nómina a registros de la plantilla estándar."""
    extension = ruta.suffix.lower()
    if extension == ".pdf":
        if tiene_texto(ruta):
            return extraer_pdf_texto(ruta)
        return extraer_escaneado(ruta)
    if extension in EXTENSIONES_IMAGEN:
        return extraer_foto(ruta)
    raise FormatoNoSoportado(f"Extensión {extension!r} no corresponde a un documento no estructurado.")
