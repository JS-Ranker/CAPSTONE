"""Partes comunes de los informes de deudores: títulos de columnas, encabezado y totales.

Los formatos de encabezado ("Lote: …") y totales ("TOTALES Registros: … Monto total: …") son
los de los documentos simulados; si la TGR usa otros, se ajustan aquí.
"""
import difflib
import re
import unicodedata

from .normalizacion import limpiar, normalizar_fecha, normalizar_monto
from .plantilla import ResultadoExtraccion

# Títulos que puede traer el documento para cada columna de la plantilla (sin tildes, en minúscula).
TITULOS = {
    "rut": ("rut", "rut deudor"),
    "nombre": ("nombre", "nombre deudor", "nombre cliente"),
    "id_demanda": ("id demanda", "id demanda*", "demanda"),
    "n_resolucion": ("n resolucion", "n° resolucion", "nº resolucion", "no resolucion", "resolucion"),
    "monto_solicitado": ("monto solicitado", "monto"),
    "tipo_embargo": ("tipo embargo", "tipo"),
    "expediente": ("expediente", "rol"),
    "tesoreria": ("tesoreria",),
    "fecha_oficio": ("fecha oficio", "fecha"),
}
_COLUMNA_POR_TITULO = {titulo: columna for columna, titulos in TITULOS.items() for titulo in titulos}

_LOTE = re.compile(r"Lote:\s*(\S+)")
_FECHA = re.compile(r"Fecha de generaci[oó]n:\s*(\S+)")
_REGISTROS = re.compile(r"Registros:\s*(\d+)")
# \W+ entre las partes: el OCR a veces agrega signos que no están en el documento ("TOTALES — Registros").
_TOTALES = re.compile(r"TOTALES\W+Registros:\s*(\d+)\W+Monto total:\s*(\$?\s*[\d.,]+)")


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def columna_desde_titulo(titulo: str | None, tolerante: bool = False) -> str | None:
    """Columna de la plantilla que corresponde a un título. `tolerante` admite errores de OCR."""
    clave = _sin_tildes(limpiar(titulo)).lower().replace("_", " ")
    if clave in _COLUMNA_POR_TITULO:
        return _COLUMNA_POR_TITULO[clave]
    if tolerante and len(clave) >= 4:
        parecidos = difflib.get_close_matches(clave, _COLUMNA_POR_TITULO, n=1, cutoff=0.75)
        return _COLUMNA_POR_TITULO[parecidos[0]] if parecidos else None
    return None


def leer_encabezado_y_totales(resultado: ResultadoExtraccion, texto: str) -> None:
    if coincidencia := _LOTE.search(texto):
        resultado.lote = coincidencia.group(1)
    if coincidencia := _FECHA.search(texto):
        resultado.fecha_documento = normalizar_fecha(coincidencia.group(1))
    if coincidencia := _TOTALES.search(texto):
        resultado.cantidad_declarada = int(coincidencia.group(1))
        resultado.suma_declarada = int(normalizar_monto(coincidencia.group(2)))
    elif coincidencia := _REGISTROS.search(texto):
        resultado.cantidad_declarada = int(coincidencia.group(1))
