"""Regla de descuento del cruce con Banco Genérico (RF04), sin base de datos."""
from datetime import date
from decimal import Decimal

from app.modulos.cruce.reglas import (DESCONTADO, NO_DESCONTADO, PARCIAL, REVISION, Cuenta, Deuda,
                                      calcular)

UTM = Decimal("70000")  # 0,5 UTM = 35.000


def deuda(id_caso, monto, rut="40000001", fecha=date(2026, 1, 10), revision=False):
    return Deuda(id_caso=id_caso, rut=rut, monto=None if monto is None else Decimal(monto), fecha_oficio=fecha,
                 revision_manual=revision)


def cuenta(id_cuenta, saldo, rut="40000001"):
    return Cuenta(id_cuenta=id_cuenta, rut=rut, numero=f"CTA{id_cuenta}", saldo=Decimal(saldo))


def por_caso(resultados):
    return {r.id_caso: r for r in resultados}


def test_no_es_cliente():
    r = calcular([deuda(1, 100_000)], [], UTM)[0]
    assert r.resultado == NO_DESCONTADO
    assert r.cliente is False
    assert r.descontado == 0 and r.pendiente == 100_000
    assert "no es cliente" in r.motivo.lower()


def test_saldo_menor_a_media_utm_no_descuenta_nada():
    r = calcular([deuda(1, 100_000)], [cuenta(1, 20_000), cuenta(2, 14_999)], UTM)[0]
    assert r.resultado == NO_DESCONTADO
    assert r.saldo_total == 34_999
    assert r.bajo_media_utm is True
    assert r.descontado == 0 and r.descuentos == ()
    assert "0,5 UTM" in r.motivo


def test_saldo_igual_a_media_utm_si_descuenta():
    r = calcular([deuda(1, 100_000)], [cuenta(1, 35_000)], UTM)[0]
    assert r.resultado == PARCIAL
    assert r.bajo_media_utm is False
    assert r.descontado == 35_000 and r.pendiente == 65_000


def test_saldo_alcanza_descuenta_la_deuda_completa():
    r = calcular([deuda(1, 80_000)], [cuenta(1, 500_000)], UTM)[0]
    assert r.resultado == DESCONTADO
    assert r.descontado == 80_000 and r.pendiente == 0
    assert r.descuentos == ((1, Decimal(80_000)),)


def test_saldo_no_alcanza_descuenta_todo_el_saldo():
    r = calcular([deuda(1, 300_000)], [cuenta(1, 120_000)], UTM)[0]
    assert r.resultado == PARCIAL
    assert r.descontado == 120_000 and r.pendiente == 180_000


def test_se_suma_el_saldo_de_todas_las_cuentas_y_se_parte_por_la_de_mayor_saldo():
    r = calcular([deuda(1, 250_000)], [cuenta(1, 30_000), cuenta(2, 200_000), cuenta(3, 100_000)], UTM)[0]
    assert r.saldo_total == 330_000
    assert r.descuentos == ((2, Decimal(200_000)), (3, Decimal(50_000)))


def test_cuentas_de_otros_ruts_no_cuentan():
    r = calcular([deuda(1, 50_000)], [cuenta(1, 1_000_000, rut="40000002")], UTM)[0]
    assert r.cliente is False


def test_varias_deudas_del_mismo_rut_de_la_mas_antigua_a_la_mas_nueva():
    resultados = por_caso(calcular(
        [deuda(1, 100_000, fecha=date(2026, 3, 1)),
         deuda(2, 100_000, fecha=date(2026, 1, 1)),
         deuda(3, 100_000, fecha=date(2026, 2, 1))],
        [cuenta(1, 150_000)], UTM))
    assert resultados[2].resultado == DESCONTADO        # la más antigua
    assert resultados[3].descontado == 50_000           # la que sigue: lo que queda
    assert resultados[3].resultado == PARCIAL
    assert resultados[1].resultado == NO_DESCONTADO     # la más nueva: ya no queda saldo
    assert "más antiguas" in resultados[1].motivo


def test_la_regla_de_media_utm_se_mira_sobre_el_saldo_inicial():
    """Si el saldo inicial supera 0,5 UTM, se descuenta hasta dejar la cuenta en 0 (regla acordada)."""
    resultados = por_caso(calcular(
        [deuda(1, 90_000, fecha=date(2026, 1, 1)), deuda(2, 50_000, fecha=date(2026, 2, 1))],
        [cuenta(1, 100_000)], UTM))
    assert resultados[1].descontado == 90_000
    assert resultados[2].descontado == 10_000


def test_sin_fecha_de_oficio_va_al_final():
    resultados = por_caso(calcular(
        [deuda(1, 100_000, fecha=None), deuda(2, 100_000, fecha=date(2026, 5, 1))],
        [cuenta(1, 100_000)], UTM))
    assert resultados[2].resultado == DESCONTADO
    assert resultados[1].resultado == NO_DESCONTADO


def test_caso_en_revision_manual_no_se_cruza_ni_consume_saldo():
    resultados = por_caso(calcular(
        [deuda(1, 100_000, fecha=date(2026, 1, 1), revision=True), deuda(2, 100_000, fecha=date(2026, 2, 1))],
        [cuenta(1, 100_000)], UTM))
    assert resultados[1].resultado == REVISION
    assert resultados[1].descontado == 0
    assert resultados[2].resultado == DESCONTADO


def test_sin_monto_solicitado_queda_en_revision():
    r = calcular([deuda(1, None)], [cuenta(1, 100_000)], UTM)[0]
    assert r.resultado == REVISION
    assert "monto" in r.motivo.lower()


def test_ruts_distintos_no_comparten_saldo():
    resultados = por_caso(calcular(
        [deuda(1, 100_000, rut="40000001"), deuda(2, 100_000, rut="40000002")],
        [cuenta(1, 100_000, rut="40000001")], UTM))
    assert resultados[1].resultado == DESCONTADO
    assert resultados[2].cliente is False


def test_los_resultados_vuelven_en_el_orden_de_las_deudas():
    deudas = [deuda(3, 1_000, rut="40000003"), deuda(1, 1_000), deuda(2, 1_000, rut="40000002")]
    assert [r.id_caso for r in calcular(deudas, [], UTM)] == [3, 1, 2]
