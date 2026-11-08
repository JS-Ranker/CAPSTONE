"""Pruebas del panel de monitoreo (RF06): los indicadores salen de lo que hay en la base."""
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.modulos.cruce import core_bancario, servicio
from app.modulos.recepcion import api as recepcion_api
from app.modulos.reportes.panel import indicadores
from tests.test_informe_tgr import CUENTAS, UTM
from tests.test_resoluciones import recorrer


def test_el_panel_vacio_muestra_ceros(conexion_etl):
    datos = indicadores(conexion_etl)

    assert datos["informes"]["total"] == 0 and datos["casos"]["total"] == 0
    assert datos["cruce"]["informes"] == 0 and datos["cruce"]["monto_descontado"] == 0
    assert datos["por_mes"] == [] and datos["ultimos_informes"] == []


def test_el_panel_refleja_informes_casos_y_cruce(conexion_etl, almacen):
    core_bancario.cargar(conexion_etl, core_bancario.leer(CUENTAS), CUENTAS.name)
    servicio.fijar_utm(conexion_etl, servicio.periodo_de(datetime.now()), UTM)
    cruzado = recorrer(conexion_etl, almacen, "01_resolucion_pdf_texto.pdf")
    sin_monto = recorrer(conexion_etl, almacen, "17_resolucion_sin_monto.xlsx")  # el ETL lo rechaza

    datos = indicadores(conexion_etl)

    assert datos["informes"]["total"] == 2
    assert datos["informes"]["por_estado"]["Procesado"] == 2
    assert datos["casos"]["total"] == 1 and datos["casos"]["rechazados_etl"] == 1
    assert datos["cruce"]["informes"] == 1 and datos["cruce"]["casos"] == 1
    assert datos["cruce"]["descontados"] == 1 and datos["cruce"]["monto_descontado"] > 0
    assert datos["excepciones_pendientes"]["rechazo"] == 1
    assert len(datos["por_mes"]) == 1 and datos["por_mes"][0]["informes"] == 1
    ids = [i["id_archivo"] for i in datos["ultimos_informes"]]
    assert ids == [sin_monto, cruzado]
    assert datos["ultimos_informes"][1]["con_descuento"] == 1 and datos["ultimos_informes"][0]["con_descuento"] is None


def test_volver_a_cruzar_no_duplica_los_montos_del_panel(conexion_etl, almacen):
    core_bancario.cargar(conexion_etl, core_bancario.leer(CUENTAS), CUENTAS.name)
    servicio.fijar_utm(conexion_etl, servicio.periodo_de(datetime.now()), UTM)
    informe = recorrer(conexion_etl, almacen, "01_resolucion_pdf_texto.pdf")
    antes = indicadores(conexion_etl)["cruce"]["monto_descontado"]

    servicio.cruzar_informe(conexion_etl, informe)

    assert indicadores(conexion_etl)["cruce"]["monto_descontado"] == antes


def test_api_del_panel(conexion_etl):
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion_etl
    try:
        cliente = TestClient(app)
        respuesta = cliente.get("/api/reportes/panel")
        assert respuesta.status_code == 200 and respuesta.json()["informes"]["total"] == 0
        assert cliente.get("/api/reportes/panel", params={"meses": 0}).status_code == 422
    finally:
        app.dependency_overrides.clear()
