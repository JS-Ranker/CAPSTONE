"""Extracción de los informes de deudores de la TGR a filas (una por deudor), con nivel de confianza.

Formatos: PDF con texto (tablas, sin OCR), PDF escaneado y fotografía (OCR local con Tesseract),
y Excel, CSV, TXT y Word (lectura directa, sin OCR).

Requerimientos: RF02, RF12, RN04, RN05
Responsable: Héctor Sanhueza

Uso:
    resultado = extraer(Path("informe.pdf"))
    resultado.estado                # 'Normalizado' o 'Error de Extracción'
    resultado.registros[0].requiere_revision
"""
from pathlib import Path

from .estructurado import TIPOS as TIPOS_ESTRUCTURADOS
from .estructurado import extraer_estructurado
from .foto import extraer_foto
from .ocr import extraer_escaneado
from .pdf_texto import extraer_pdf_texto, tiene_texto
from .plantilla import COLUMNAS_PLANTILLA, ResultadoExtraccion, escribir_plantilla

__all__ = ["COLUMNAS_PLANTILLA", "FormatoNoSoportado", "ResultadoExtraccion", "escribir_plantilla", "extraer"]

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png"}


class FormatoNoSoportado(Exception):
    """El documento no es un formato de informe que este módulo pueda leer."""


def extraer(ruta: Path) -> ResultadoExtraccion:
    """Lee un informe de deudores en cualquiera de los formatos admitidos."""
    extension = ruta.suffix.lower()
    if extension == ".pdf":
        if tiene_texto(ruta):
            return extraer_pdf_texto(ruta)
        return extraer_escaneado(ruta)
    if extension in EXTENSIONES_IMAGEN:
        return extraer_foto(ruta)
    if extension in TIPOS_ESTRUCTURADOS:
        return extraer_estructurado(ruta)
    if extension == ".xls":
        return ResultadoExtraccion(tipo_documento="Excel", errores=[
            "El formato .xls (Excel 97-2003) no se puede leer: pida el informe en .xlsx o guárdelo como .xlsx."])
    raise FormatoNoSoportado(f"Extensión {extension!r} no corresponde a un informe que se pueda leer.")
