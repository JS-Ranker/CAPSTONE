"""Pruebas de los avisos a clientes con descuento (RF07): lista y texto, sin enviar correos."""
import io
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from app.modulos.cruce import core_bancario, servicio
from app.modulos.recepcion import api as recepcion_api
from app.modulos.reportes import avisos
from tests.test_informe_tgr import CUENTAS, UTM, resultado
from tests.test_resoluciones import recorrer


def cruce_de_prueba():
    cuenta = {"cuenta": "111", "tipo": "Cuenta RUT", "monto": Decimal(100_000)}
    otra = {"cuenta": "222", "tipo": "Cuenta corriente", "monto": Decimal(50_000)}
    return {"resultados": [
        resultado("40000001", "ANA PEREZ", "Descontado", 100_000, 250_000, 100_000, "ok", descuentos=[cuenta]),
        resultado("40000001", "ANA PEREZ", "Descontado parcial", 80_000, 50_000, 50_000, "parcial", descuentos=[otra]),
        resultado("40000002", "LUIS SOTO", "No descontado", 200_000, 20_000, 0, "bajo 0,5 UTM"),
        resultado("40000003", "JOSE ROJAS", "No descontado", 90_000, 0, 0, "no es cliente", cliente=False),
    ]}


def test_solo_reciben_aviso_los_clientes_con_descuento_y_se_juntan_por_rut():
    lista = avisos.armar_avisos(cruce_de_prueba())

    assert len(lista) == 1
    aviso = lista[0]
    assert aviso["rut"] == "40.000.001-5" and aviso["descontado"] == 150_000 and aviso["pendiente"] == 30_000
    assert "Cuenta RUT N° 111: $100.000" in aviso["cuentas"] and "Cuenta corriente N° 222: $50.000" in aviso["cuentas"]
    assert "Estimado/a ANA PEREZ" in aviso["texto"] and "$150.000" in aviso["texto"]
    assert "saldo de la deuda por $30.000" in aviso["texto"]


def test_el_excel_de_avisos_y_el_caso_sin_avisos():
    libro = load_workbook(io.BytesIO(avisos.construir_excel(avisos.armar_avisos(cruce_de_prueba()), "informe.pdf")))
    filas = list(libro["Avisos"].iter_rows(values_only=True))
    assert filas[0][0] == "RUT" and len(filas) == 2 and filas[1][3] == 150_000
    assert libro["Informe"]["B2"].value == 1

    vacio = load_workbook(io.BytesIO(avisos.construir_excel([], "informe.pdf")))
    assert "no hay avisos" in vacio["Avisos"]["A2"].value


def test_api_de_avisos_con_el_banco_simulado(conexion_etl, almacen):
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion_etl
    try:
        cliente = TestClient(app)
        core_bancario.cargar(conexion_etl, core_bancario.leer(CUENTAS), CUENTAS.name)
        servicio.fijar_utm(conexion_etl, servicio.periodo_de(datetime.now()), UTM)
        id_archivo = recorrer(conexion_etl, almacen, "01_resolucion_pdf_texto.pdf")  # su saldo cubre la deuda

        respuesta = cliente.get(f"/api/reportes/informes/{id_archivo}/avisos-clientes.xlsx")

        assert respuesta.status_code == 200
        assert "avisos_clientes_01_resolucion_pdf_texto.xlsx" in respuesta.headers["content-disposition"]
        filas = list(load_workbook(io.BytesIO(respuesta.content))["Avisos"].iter_rows(min_row=2, values_only=True))
        assert len(filas) == 1 and filas[0][3] > 0
        assert cliente.get("/api/reportes/informes/999999/avisos-clientes.xlsx").status_code == 404
    finally:
        app.dependency_overrides.clear()
