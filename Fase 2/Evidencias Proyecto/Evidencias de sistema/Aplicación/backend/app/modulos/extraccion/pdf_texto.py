"""Extracción directa de tablas en PDF con texto seleccionable (RF12, sin OCR)."""
from pathlib import Path

import pdfplumber

from .documento import columna_desde_titulo, leer_encabezado_y_totales
from .normalizacion import limpiar, normalizar
from .plantilla import COLUMNAS_PLANTILLA, RegistroExtraido, ResultadoExtraccion


def tiene_texto(ruta: Path) -> bool:
    """True si el PDF trae texto seleccionable; False si es solo imagen (escaneado)."""
    with pdfplumber.open(ruta) as pdf:
        return any((pagina.extract_text() or "").strip() for pagina in pdf.pages)


def extraer_pdf_texto(ruta: Path) -> ResultadoExtraccion:
    resultado = ResultadoExtraccion(tipo_documento="PDF con texto")
    with pdfplumber.open(ruta) as pdf:
        textos = [pagina.extract_text() or "" for pagina in pdf.pages]
        tablas = [tabla for pagina in pdf.pages for tabla in pagina.extract_tables()]

    leer_encabezado_y_totales(resultado, "\n".join(textos))

    columnas: list[str | None] | None = None
    for tabla in tablas:
        for fila in tabla:
            posibles = [columna_desde_titulo(celda) for celda in fila]
            if set(COLUMNAS_PLANTILLA) <= set(posibles):  # fila de títulos (se repite en cada página)
                columnas = posibles
                continue
            if columnas is None or not any(limpiar(celda) for celda in fila):
                continue
            valores = {col: normalizar(col, celda) for col, celda in zip(columnas, fila) if col}
            resultado.registros.append(RegistroExtraido(valores, {col: 100.0 for col in COLUMNAS_PLANTILLA}))

    if columnas is None:
        resultado.errores.append("No se encontró una tabla con las columnas de la plantilla estándar.")
        return resultado
    resultado.verificar_totales()
    return resultado
