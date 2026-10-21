"""Tendencias de rechazo y calidad de un informe comparado con los anteriores (RF08), sin base de datos.

"Interpretar tendencias de rechazo": un informe con muchos más rechazos que lo habitual, o donde un mismo motivo
domina, suele indicar un problema de origen (la TGR cambió el formato, el documento llegó en mala calidad) más
que deudores con datos malos. Lo mismo con muchos datos dudosos del OCR.
"""
import re
from collections import Counter
from dataclasses import dataclass
from statistics import mean

from .deteccion import ALTO, BAJO, MEDIO

TENDENCIA, CALIDAD = "Tendencia de rechazo", "Calidad del documento"
MINIMO_FILAS = 5  # en informes muy chicos los porcentajes no dicen mucho

# Qué hacer según el motivo que más se repite (prefijo del motivo del ETL).
SUGERENCIAS = {
    "RUT o DV inválido": "Verifique los RUT contra el documento original; si el error viene de la TGR, pida que "
                         "reenvíe el informe corregido.",
    "EXPEDIENTE sin formato": "Revise si la TGR cambió el formato del expediente (número-año localidad).",
    "FECHA": "Revise el formato de las fechas del informe (se espera dd-mm-aaaa).",
    "Falta MONTO SOLICITADO": "Pida a la TGR los montos faltantes antes de procesar los descuentos.",
    "MONTO SOLICITADO no es": "Revise cómo vienen escritos los montos (se esperan números enteros, sin texto).",
}


@dataclass(frozen=True)
class Hallazgo:
    tipo: str
    nivel: str
    titulo: str
    detalle: str
    sugerencia: str | None = None


def motivo_base(motivo: str) -> str:
    """Motivo sin el dato del deudor: 'RUT o DV inválido (4600-1)' -> 'RUT o DV inválido'."""
    return re.sub(r"\s*\(.*\)\s*$", "", motivo or "").strip()


def _porcentaje(parte: int, total: int) -> float:
    return 100.0 * parte / total if total else 0.0


def _sugerencia_para(motivo: str) -> str | None:
    return next((texto for prefijo, texto in SUGERENCIAS.items() if motivo.startswith(prefijo)), None)


def tendencias(actual: dict, anteriores: list[dict]) -> list[Hallazgo]:
    """`actual` y cada anterior: {"filas", "rechazadas", "en_revision", "motivos": Counter, "tipo_documento"}."""
    hallazgos = []
    filas = actual["filas"]
    if filas < MINIMO_FILAS:
        return hallazgos

    tasa = _porcentaje(actual["rechazadas"], filas)
    tasas_previas = [_porcentaje(a["rechazadas"], a["filas"]) for a in anteriores if a["filas"] >= MINIMO_FILAS]
    habitual = mean(tasas_previas) if tasas_previas else None
    if tasa >= 10 and (habitual is None or tasa >= 2 * habitual):
        nivel = ALTO if tasa >= 40 else MEDIO if tasa >= 20 else BAJO
        comparacion = (f"lo habitual es {habitual:.0f}% en los {len(tasas_previas)} informes anteriores"
                       if habitual is not None else "no hay informes anteriores para comparar")
        motivos: Counter = actual["motivos"]
        principal, veces = motivos.most_common(1)[0] if motivos else ("", 0)
        detalle = f"Se rechazaron {actual['rechazadas']} de {filas} deudores ({tasa:.0f}%); {comparacion}."
        if veces:
            detalle += f" El motivo más frecuente es «{principal}» ({veces} de {actual['rechazadas']})."
        hallazgos.append(Hallazgo(TENDENCIA, nivel, f"Rechazos fuera de lo habitual: {tasa:.0f}% del informe",
                                  detalle, _sugerencia_para(principal) if veces else None))

    revision = _porcentaje(actual["en_revision"], filas)
    if revision >= 15:
        nivel = MEDIO if revision >= 30 else BAJO
        sugerencia = None
        if actual.get("tipo_documento") in ("PDF escaneado", "Imagen"):
            sugerencia = ("El documento llegó como imagen: pida a la TGR el informe en Excel o en PDF con texto, que "
                          "se leen sin errores.")
        hallazgos.append(Hallazgo(
            CALIDAD, nivel, f"Muchos datos dudosos: {revision:.0f}% del informe quedó para revisión manual",
            f"{actual['en_revision']} de {filas} deudores tienen datos vacíos o leídos con poca confianza.",
            sugerencia,
        ))
    return hallazgos
