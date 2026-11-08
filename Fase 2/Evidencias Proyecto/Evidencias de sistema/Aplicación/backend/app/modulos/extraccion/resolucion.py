"""Lectura de las resoluciones de retención de la TGR: un deudor por documento (RF12, RN05, CU12).

Es el documento que la TGR envía realmente: una resolución de dos páginas con los datos del deudor repartidos
en el texto (expediente y RUT en los "vistos", monto en el "resuelvo", ID de demanda, N° de resolución, firma y
fecha en la última página). Se lee igual en todos los formatos: PDF con texto, PDF escaneado, JPG o PNG (OCR
local), Word y TXT (texto), y Excel o CSV (pares campo/valor). Cada documento da un solo registro, en las mismas
columnas de la plantilla estándar, para que el resto del proceso (ETL, cruce, IA) no cambie.
"""
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from .normalizacion import normalizar, rut_valido
from .plantilla import COLUMNAS_PLANTILLA, RegistroExtraido, ResultadoExtraccion

RUT_TGR = "60805000-0"  # el RUT de la propia Tesorería aparece en el texto y no es el del deudor
_N = r"N\s*[°ºo*'’`´?\"”]?\s*:?\s*"  # el OCR lee "N°" como "N*", "N'", "N?" o "N”"
_MAYUSCULAS = r"A-ZÁÉÍÓÚÑ"
_RUT = re.compile(r"\bRUT\s*:?\s*([\d.,]{7,12})\s*-\s*([\dKk])\b", re.I)
_NOMBRE = re.compile(rf"\bcontra\s+de\s+(.+?)\s*,\s*RUT\b", re.I | re.S)
_NOMBRE_ANTES_DEL_RUT = re.compile(rf"\n\s*([{_MAYUSCULAS} .'-]{{5,}}?)\s*,\s*RUT\s*:", re.I)
_ID_DEMANDA = re.compile(r"\b[I1l]D\s*DEMANDA\s*:?\s*(\d{5,})", re.I)
_N_RESOLUCION = re.compile(rf"\bRESOLUCI[OÓ]N\s*{_N}(\d{{5,}})", re.I)
_ROL = re.compile(rf"\bRol\s*{_N}(\d+\s*-\s*\d{{4}})(?:\s+de\s+([{_MAYUSCULAS} ]+?))?\s*[,.;]", re.I)
_MONTO = re.compile(r"\$\s*([\d.,]+)\s*,\s*correspondiente", re.I)
_MONTO_CUALQUIERA = re.compile(r"\$\s*([\d.]{5,})")
_TESORERIA = re.compile(r"TESORER[IÍ]A\s+REGIONAL\s+DE\s+([^\n|¡!]+)", re.I)
_SECCION_DEL_PIE = re.compile(r"\s+SECCI[OÓ]N\b.*$", re.I)
_FECHA = re.compile(r"\bFecha\s*:\s*(\d{2}\s*[/-]\s*\d{2}\s*[/-]\s*\d{4})", re.I)
_FECHA_EN_PALABRAS = re.compile(r"\ba\s+([a-z ]+?)\s+de\s+([a-z]+)\s+de\s+(\d{4})\b")
_RETENCION = re.compile(r"\bret[eé]ng(?:ase|a)\b|\bretenci[oó]n\b", re.I)
_ES_RESOLUCION = re.compile(r"RESOLUCI[OÓ]N\s*N|\b[I1l]D\s*DEMANDA", re.I)

_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_UNIDADES = {"uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
             "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
             "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
             "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
             "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "treinta y uno": 31}

# Si el RUT leído pasa Módulo 11, un error de lectura es muy improbable: con esta confianza basta (igual que en ocr.py).
CONFIANZA_MINIMA_RUT_VERIFICADO = 80.0
UMBRAL_CONFIANZA_RUT = 90.0


@dataclass
class TextoLeido:
    """Texto de un documento y, si viene de OCR, la confianza (0-100) de cada palabra según su posición."""
    texto: str
    palabras: list[tuple[int, int, float]] = field(default_factory=list)  # (inicio, fin, confianza)

    def confianza(self, inicio: int, fin: int) -> float:
        """La del tramo menos confiable; 100 si el texto no viene de OCR."""
        if not self.palabras:
            return 100.0
        tramo = [conf for ini, fi, conf in self.palabras if ini < fin and fi > inicio]
        return min(tramo) if tramo else 0.0


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def es_resolucion(texto: str) -> bool:
    """True si el texto es una resolución de la TGR y no un informe con tabla."""
    return len(_ES_RESOLUCION.findall(texto)) >= 2


def _fecha_oficio(texto: str) -> tuple[str, tuple[int, int]] | None:
    fechas = list(_FECHA.finditer(texto))
    if fechas:
        ultima = fechas[-1]  # la de la firma, en la última página
        return re.sub(r"\s", "", ultima.group(1)).replace("/", "-"), ultima.span(1)
    en_palabras = _FECHA_EN_PALABRAS.search(_sin_tildes(texto.lower()))
    if en_palabras:
        dia = _UNIDADES.get(en_palabras.group(1).strip())
        mes = _MESES.get(en_palabras.group(2))
        if dia and mes:
            return f"{dia:02d}-{mes:02d}-{en_palabras.group(3)}", en_palabras.span()
    return None


def _rut_del_deudor(texto: str) -> re.Match | None:
    for coincidencia in _RUT.finditer(texto):
        rut = normalizar("rut", f"{coincidencia.group(1)}-{coincidencia.group(2)}")
        if rut != RUT_TGR:
            return coincidencia
    return None


def leer_campos(leido: TextoLeido) -> RegistroExtraido:
    """Datos de la resolución en las columnas de la plantilla, con la confianza de cada uno."""
    texto = leido.texto
    valores = dict.fromkeys(COLUMNAS_PLANTILLA, "")
    confianzas = dict.fromkeys(COLUMNAS_PLANTILLA, 0.0)

    def poner(columna: str, valor: str, inicio: int, fin: int) -> None:
        valores[columna] = normalizar(columna, valor)
        confianzas[columna] = leido.confianza(inicio, fin)

    if rut := _rut_del_deudor(texto):
        poner("rut", f"{rut.group(1)}-{rut.group(2)}", *rut.span())
        if confianzas["rut"] >= CONFIANZA_MINIMA_RUT_VERIFICADO and rut_valido(valores["rut"]):
            confianzas["rut"] = max(confianzas["rut"], UMBRAL_CONFIANZA_RUT)
    nombre = _NOMBRE.search(texto) or _NOMBRE_ANTES_DEL_RUT.search(texto)
    if nombre:
        poner("nombre", nombre.group(1), *nombre.span(1))
    if demanda := _ID_DEMANDA.search(texto):
        poner("id_demanda", demanda.group(1), *demanda.span(1))
    if resolucion := _N_RESOLUCION.search(texto):
        poner("n_resolucion", resolucion.group(1), *resolucion.span(1))
    if rol := _ROL.search(texto):
        localidad = f" {' '.join(rol.group(2).split())}" if rol.group(2) else ""
        poner("expediente", re.sub(r"\s", "", rol.group(1)) + localidad, *rol.span(1))
    if monto := _MONTO.search(texto) or _MONTO_CUALQUIERA.search(texto):
        poner("monto_solicitado", monto.group(1), *monto.span(1))
    if tesorerias := list(_TESORERIA.finditer(texto)):
        ultima = tesorerias[-1]  # la de la firma; antes está el pie de página con "| Sección Unidades de Cobro"
        nombre_tesoreria = _SECCION_DEL_PIE.sub("", " ".join(ultima.group(1).split())).upper()
        poner("tesoreria", f"TESORERÍA REGIONAL DE {nombre_tesoreria}", *ultima.span(1))
    if fecha := _fecha_oficio(texto):
        poner("fecha_oficio", fecha[0], *fecha[1])
    if retencion := _RETENCION.search(texto):
        poner("tipo_embargo", "RETENCIÓN", *retencion.span())
    return RegistroExtraido(valores, confianzas)


def resultado_desde_texto(leido: TextoLeido, tipo_documento: str) -> ResultadoExtraccion:
    """Un documento, un deudor. Sin ningún dato identificatorio se manda el documento completo a revisión."""
    resultado = ResultadoExtraccion(tipo_documento=tipo_documento)
    registro = leer_campos(leido)
    valores = registro.valores
    if not (valores["rut"] or valores["id_demanda"] or valores["n_resolucion"]):
        resultado.errores.append("No se encontraron los datos de una resolución de la TGR (RUT, ID de demanda ni "
                                 "N° de resolución).")
        return resultado
    resultado.registros.append(registro)
    resultado.fecha_documento = valores["fecha_oficio"] or None
    return resultado


def resultado_desde_pares(filas: list[list[str]], tipo_documento: str,
                          columna_de: Callable[[str], str | None]) -> ResultadoExtraccion | None:
    """Excel o CSV de una resolución: filas "campo, valor". None si el archivo no tiene ese formato."""
    valores = dict.fromkeys(COLUMNAS_PLANTILLA, "")
    for fila in filas:
        celdas = [c for c in fila if c.strip()]
        if len(celdas) < 2:
            continue
        columna = columna_de(celdas[0])
        if columna and not valores[columna]:
            valores[columna] = normalizar(columna, celdas[1])
    if sum(1 for valor in valores.values() if valor) < 5:
        return None
    resultado = ResultadoExtraccion(tipo_documento=tipo_documento)
    confianzas = {c: 100.0 if valores[c] else 0.0 for c in COLUMNAS_PLANTILLA}
    resultado.registros.append(RegistroExtraido(valores, confianzas))
    resultado.fecha_documento = valores["fecha_oficio"] or None
    return resultado
