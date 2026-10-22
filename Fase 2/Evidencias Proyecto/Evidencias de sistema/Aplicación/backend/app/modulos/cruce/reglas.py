"""Regla de descuento del cruce con Banco Genérico (RF04), sin base de datos.

Acordada por el equipo el 12-10-2026:
- El saldo del cliente es la suma de sus cuentas activas. Si es menor a 0,5 UTM, no se descuenta nada.
- Si es 0,5 UTM o más, se descuenta lo menor entre el saldo y la deuda, partiendo por la cuenta de mayor saldo.
- Varias deudas del mismo RUT se cubren de la más antigua (fecha del oficio) a la más nueva; las sin fecha, al final.
- No se guarda deuda pendiente entre meses: la TGR reenvía el informe cada mes.
- El sistema solo calcula e informa; el cargo real lo hace el core bancario.

Los casos marcados para revisión manual (o sin monto) no se cruzan ni consumen saldo hasta que el analista los
resuelva en la Bandeja de Excepciones y se vuelva a cruzar el informe.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

DESCONTADO, PARCIAL, NO_DESCONTADO, REVISION = "Descontado", "Descontado parcial", "No descontado", "En revisión"
RESULTADOS = (DESCONTADO, PARCIAL, NO_DESCONTADO, REVISION)
CERO = Decimal(0)


@dataclass(frozen=True)
class Deuda:
    id_caso: int
    rut: str
    monto: Decimal | None
    fecha_oficio: date | None
    revision_manual: bool = False


@dataclass(frozen=True)
class Cuenta:
    """Cuenta activa del core bancario."""
    id_cuenta: int
    rut: str
    numero: str
    saldo: Decimal


@dataclass(frozen=True)
class Resultado:
    id_caso: int
    resultado: str
    cliente: bool
    saldo_total: Decimal          # suma de las cuentas activas del RUT (0 si no es cliente)
    bajo_media_utm: bool | None   # None si no es cliente
    monto: Decimal | None
    descontado: Decimal
    pendiente: Decimal
    motivo: str
    descuentos: tuple[tuple[int, Decimal], ...] = ()  # (id_cuenta, monto), en el orden en que se descuenta


def pesos(valor: Decimal) -> str:
    """Decimal('1234567.00') -> '$ 1.234.567'."""
    return "$ " + f"{valor:,.0f}".replace(",", ".")


def _orden(deuda: Deuda) -> tuple:
    return (deuda.fecha_oficio is None, deuda.fecha_oficio or date.max, deuda.id_caso)


def calcular(deudas: list[Deuda], cuentas: list[Cuenta], valor_utm: Decimal) -> list[Resultado]:
    """Resultado de cada deuda, en el mismo orden en que vienen."""
    media_utm = valor_utm / 2
    cuentas_por_rut: dict[str, list[Cuenta]] = {}
    for cuenta in cuentas:
        cuentas_por_rut.setdefault(cuenta.rut, []).append(cuenta)
    deudas_por_rut: dict[str, list[Deuda]] = {}
    for deuda in deudas:
        deudas_por_rut.setdefault(deuda.rut, []).append(deuda)

    resultados: dict[int, Resultado] = {}
    for rut, del_rut in deudas_por_rut.items():
        propias = sorted(cuentas_por_rut.get(rut, []), key=lambda c: (-c.saldo, c.id_cuenta))
        saldo_total = sum((c.saldo for c in propias), CERO)
        disponible = {c.id_cuenta: c.saldo for c in propias}
        bajo = saldo_total < media_utm if propias else None
        for deuda in sorted(del_rut, key=_orden):
            resultados[deuda.id_caso] = _resultado(deuda, propias, saldo_total, bajo, disponible, media_utm)
    return [resultados[d.id_caso] for d in deudas]


def _resultado(deuda: Deuda, cuentas: list[Cuenta], saldo_total: Decimal, bajo: bool | None,
               disponible: dict[int, Decimal], media_utm: Decimal) -> Resultado:
    def sin_descuento(resultado: str, motivo: str) -> Resultado:
        return Resultado(deuda.id_caso, resultado, bool(cuentas), saldo_total, bajo, deuda.monto, CERO,
                         deuda.monto if deuda.monto is not None else CERO, motivo)

    if deuda.monto is None:
        return sin_descuento(REVISION, "Sin monto solicitado: se cruza cuando el analista lo complete.")
    if deuda.revision_manual:
        return sin_descuento(REVISION, "Caso marcado para revisión manual: se cruza cuando el analista lo resuelva.")
    if not cuentas:
        return sin_descuento(NO_DESCONTADO, "No es cliente de Banco Genérico.")
    if bajo:
        return sin_descuento(NO_DESCONTADO, f"Saldo total {pesos(saldo_total)} menor a 0,5 UTM "
                                            f"({pesos(media_utm)}).")

    por_descontar = deuda.monto
    descuentos = []
    for cuenta in cuentas:
        if por_descontar <= 0:
            break
        monto = min(disponible[cuenta.id_cuenta], por_descontar)
        if monto > 0:
            disponible[cuenta.id_cuenta] -= monto
            por_descontar -= monto
            descuentos.append((cuenta.id_cuenta, monto))
    descontado = deuda.monto - por_descontar
    if not descontado:
        return sin_descuento(NO_DESCONTADO, "Sin saldo disponible: lo cubrieron deudas más antiguas del mismo RUT.")
    if por_descontar:
        motivo = f"El saldo alcanzó para {pesos(descontado)} de {pesos(deuda.monto)}."
        resultado = PARCIAL
    else:
        motivo = "Deuda cubierta con el saldo del cliente."
        resultado = DESCONTADO
    return Resultado(deuda.id_caso, resultado, True, saldo_total, bajo, deuda.monto, descontado, por_descontar,
                     motivo, tuple(descuentos))
