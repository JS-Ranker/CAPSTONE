"""Normalización de los valores extraídos al formato de la plantilla estándar de carga.

Solo da formato: no decide si un valor es válido (eso es del motor de validaciones, RF03).
Cuando un valor no se puede normalizar se devuelve el texto original limpio, para que la
validación lo marque como inválido en vez de perderlo.
"""
import re
from datetime import datetime

_RUT = re.compile(r"^(\d{1,8})-?([\dK])$")
_FORMATOS_FECHA = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")


def limpiar(texto: str | None) -> str:
    """Quita espacios sobrantes y saltos de línea."""
    return " ".join((texto or "").split())


def normalizar_rut(texto: str | None) -> str:
    """'12.345.678-k' o ' 12345678K ' -> '12345678-K'. Acepta ',' por '.' (confusión típica del OCR)."""
    limpio = limpiar(texto)
    compacto = limpio.replace(".", "").replace(",", "").replace(" ", "").upper()
    coincidencia = _RUT.match(compacto)
    if not coincidencia:
        return limpio
    numero, dv = coincidencia.groups()
    return f"{int(numero)}-{dv}"


def rut_valido(rut: str) -> bool:
    """True si un RUT normalizado ('12345678-5') pasa el algoritmo Módulo 11.

    Aquí se usa solo como evidencia de una lectura OCR correcta; la validación de negocio
    (RN01) es responsabilidad del motor de validaciones.
    """
    coincidencia = _RUT.match(rut)
    if not coincidencia:
        return False
    numero, dv = coincidencia.groups()
    suma, factor = 0, 2
    for digito in reversed(numero):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    esperado = {11: "0", 10: "K"}.get(11 - suma % 11, str(11 - suma % 11))
    return dv == esperado


def normalizar_monto(texto: str | None) -> str:
    """'$ 1.250.000' -> '1250000'.

    Los montos son pesos chilenos, sin decimales, así que ',' también se toma como separador de
    miles: el OCR confunde a menudo el punto con la coma.
    """
    limpio = limpiar(texto)
    compacto = limpio.replace("$", "").replace(".", "").replace(",", "").replace(" ", "")
    return str(int(compacto)) if compacto.isdigit() else limpio


def normalizar_fecha(texto: str | None) -> str:
    """'15-09-2026', '15/09/2026' o '2026-09-15' -> '2026-09-15'."""
    limpio = limpiar(texto)
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(limpio, formato).date().isoformat()
        except ValueError:
            continue
    return limpio


NORMALIZADORES = {
    "rut_deudor": normalizar_rut,
    "monto": normalizar_monto,
    "fecha_origen": normalizar_fecha,
}


def normalizar(columna: str, texto: str | None) -> str:
    return NORMALIZADORES.get(columna, limpiar)(texto)
