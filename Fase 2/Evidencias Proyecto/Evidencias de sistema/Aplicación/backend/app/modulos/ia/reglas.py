"""Validaciones sugeridas por la IA que el analista aplicó (CU08 paso 5). El ETL las usa en los procesos siguientes.

Por ahora hay un tipo: monto_maximo (los casos con monto sobre el valor quedan para revisión manual).
Módulo aparte y sin dependencias del resto de la IA, para que el ETL lo pueda usar sin ciclos de importación.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text

MONTO_MAXIMO = "monto_maximo"


@dataclass(frozen=True)
class Regla:
    id_regla: int
    tipo: str
    valor: Decimal


def reglas_activas(conexion: Connection) -> list[Regla]:
    """Reglas vigentes. Si aún no se ejecutó 09_ia.sql, no hay reglas."""
    if conexion.execute(text("SELECT OBJECT_ID('ia.reglas', 'U')")).scalar_one() is None:
        return []
    filas = conexion.execute(text("SELECT id_regla, tipo, valor FROM ia.reglas WHERE activa = 1")).all()
    return [Regla(*fila) for fila in filas]


def motivo_por_reglas(monto: Decimal | None, reglas: list[Regla]) -> str | None:
    """Texto para CAMPOS FALTANTES OCR si alguna regla manda el caso a revisión; None si no aplica."""
    for regla in reglas:
        if regla.tipo == MONTO_MAXIMO and monto is not None and monto > regla.valor:
            valor = "$" + f"{regla.valor:,.0f}".replace(",", ".")
            return f"MONTO SOBRE {valor} (REGLA IA)"
    return None
