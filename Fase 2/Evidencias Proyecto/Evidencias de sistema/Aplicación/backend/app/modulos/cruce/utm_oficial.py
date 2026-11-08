"""Consulta del valor oficial de la UTM de un mes (RF04).

Fuente: mindicador.cl, que publica los indicadores del Banco Central y del SII. Solo se consulta el valor de la UTM
(no se envía ningún dato de deudores). Si la fuente no responde o el mes aún no está publicado, el analista puede
ingresar la UTM a mano.
"""
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

URL = "https://mindicador.cl/api/utm/{anio}"
FUENTE = "mindicador.cl"
TIEMPO_MAXIMO = 6  # segundos por intento: la fuente responde en ~1 s, pero a veces se cuelga
INTENTOS = 4


class UtmNoDisponible(Exception):
    """La fuente no respondió o el mes todavía no tiene UTM publicada."""


def _serie(anio: str) -> list[dict]:
    solicitud = Request(URL.format(anio=anio), headers={"Accept": "application/json", "User-Agent": "TTDH-Automation"})
    error: Exception | None = None
    for intento in range(1, INTENTOS + 1):
        try:
            with urlopen(solicitud, timeout=TIEMPO_MAXIMO) as respuesta:  # noqa: S310 - URL fija con https
                return json.load(respuesta)["serie"]
        except (URLError, TimeoutError, ValueError, KeyError, OSError) as falla:
            error = falla
            log.warning("Intento %s/%s de consultar la UTM de %s falló: %s", intento, INTENTOS, anio, falla)
    raise UtmNoDisponible(f"No se pudo consultar la UTM oficial en {FUENTE}: ingrésela a mano.") from error


def consultar(periodo: str) -> Decimal:
    """UTM oficial del mes `periodo` ('aaaa-mm')."""
    serie = _serie(periodo[:4])
    try:
        valor = next(e["valor"] for e in serie if str(e.get("fecha", ""))[:7] == periodo)
    except StopIteration:
        raise UtmNoDisponible(f"{FUENTE} aún no publica la UTM de {periodo}: ingrésela a mano.") from None
    try:
        return Decimal(str(valor))
    except InvalidOperation as error:
        raise UtmNoDisponible(f"{FUENTE} entregó un valor de UTM no válido para {periodo}.") from error
