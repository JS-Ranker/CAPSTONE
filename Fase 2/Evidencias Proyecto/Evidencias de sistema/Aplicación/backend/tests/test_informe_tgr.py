"""Pruebas del informe de respuesta a la TGR (RF07, RF11): el Excel con el resumen y el detalle del cruce."""
import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from app.modulos.cruce import core_bancario, servicio
from app.modulos.recepcion import api as recepcion_api
from app.modulos.reportes import informe_tgr
from tests.test_resoluciones import DATOS, por_nombre, recorrer

CUENTAS = DATOS / "banco_generico" / "cuentas_core_bancario.csv"
UTM = Decimal("70000")


def resultado(rut, nombre, estado, deuda, saldo, descontado, motivo, cliente=True, descuentos=()):
    return {"id_resultado": 1, "id_caso": 1, "rut": rut, "dv": "5", "nombre": nombre, "rol": "123-2026 TALCA",
            "id_demanda": "111", "n_resol": "222", "fecha_oficio": date(2026, 9, 1), "resultado": estado,
            "cliente": cliente, "saldo_total": Decimal(saldo), "monto_solicitado": Decimal(deuda),
            "monto_descontado": Decimal(descontado), "monto_pendiente": Decimal(deuda) - Decimal(descontado),
            "motivo": motivo, "descuentos": list(descuentos)}


@pytest.fixture
def datos():
    return {
        "archivo": {"nombre_archivo": "informe_octubre.pdf", "fecha_recepcion": datetime(2026, 10, 5, 9, 30),
                    "remitente": "notificaciones@tgr.cl"},
        "etl": {"filas_leidas": 5, "cargadas": 3, "rechazadas": 2, "duplicadas": 0},
        "cruce": {"id_ejecucion": 7, "fecha": datetime(2026, 10, 5, 10, 0), "periodo": "2026-10",
                  "valor_utm": Decimal("70000"), "resultados": [
                      resultado("40000001", "ANA PEREZ", "Descontado", 100_000, 250_000, 100_000, "Saldo suficiente",
                                descuentos=[{"cuenta": "111", "tipo": "Cuenta RUT", "monto": Decimal(100_000)}]),
                      resultado("40000002", "LUIS SOTO", "Descontado parcial", 500_000, 300_000, 300_000,
                                "Saldo menor que la deuda"),
                      resultado("40000003", "MARIA DIAZ", "No descontado", 200_000, 20_000, 0, "Bajo 0,5 UTM"),
                      resultado("40000004", "JOSE ROJAS", "No descontado", 90_000, 0, 0, "No es cliente",
                                cliente=False)]},
        "rechazados": [{"rut": "40000005", "dv": "1", "nom_cli": "PEDRO RIOS", "id_demanda": "333", "n_resol": "444",
                        "monto_solicitado": "", "motivo": "El monto es obligatorio"}],
    }


def test_los_totales_del_resumen(datos):
    total = informe_tgr.totales(datos)

    assert (total["recibidos"], total["validos"], total["invalidos"]) == (5, 4, 1)
    assert (total["clientes"], total["no_clientes"]) == (3, 1)
    assert (total["descontados"], total["parciales"], total["no_descontados"], total["en_revision"]) == (1, 1, 2, 0)
    assert total["monto_solicitado"] == 890_000
    assert total["monto_descontado"] == 400_000
    assert total["monto_pendiente"] == 490_000


def test_el_excel_tiene_resumen_detalle_y_no_procesados(datos):
    libro = load_workbook(io.BytesIO(informe_tgr.construir_excel(datos)))

    assert libro.sheetnames == ["Resumen", "Detalle", "No procesados"]
    resumen = {fila[0].value: fila[1].value for fila in libro["Resumen"].iter_rows(min_row=4) if fila[0].value}
    assert resumen["Informe recibido"] == "informe_octubre.pdf"
    assert resumen["Umbral de descuento (0,5 UTM)"] == 35_000
    assert resumen["Deudores recibidos"] == 5
    assert resumen["Clientes de Banco Genérico encontrados"] == 3
    assert resumen["Monto a descontar"] == 400_000

    detalle = list(libro["Detalle"].iter_rows(values_only=True))
    assert detalle[0][:2] == ("RUT", "Nombre") and len(detalle) == 5
    assert detalle[1][0] == "40.000.001-5" and detalle[1][10] == "Descontado"
    assert "Cuenta RUT N° 111: $100.000" in detalle[1][12]
    assert detalle[4][10] == "No descontado" and detalle[4][11] == "No es cliente"

    rechazados = list(libro["No procesados"].iter_rows(values_only=True))
    assert rechazados[1][0] == "40.000.005-1" and rechazados[1][5] == "El monto es obligatorio"


def test_sin_rechazados_la_hoja_lo_dice(datos):
    datos["rechazados"] = []
    libro = load_workbook(io.BytesIO(informe_tgr.construir_excel(datos)))

    assert libro["No procesados"]["A2"].value == "Ningún deudor quedó sin procesar."


def test_el_informe_de_una_resolucion_cruzada_con_el_banco_simulado(conexion_etl, almacen):
    core_bancario.cargar(conexion_etl, core_bancario.leer(CUENTAS), CUENTAS.name)
    servicio.fijar_utm(conexion_etl, servicio.periodo_de(datetime.now()), UTM)
    id_archivo = recorrer(conexion_etl, almacen, "01_resolucion_pdf_texto.pdf")  # deudor con saldo que cubre
    esperado = por_nombre("01_resolucion_pdf_texto.pdf")["deudor"]

    contenido, nombre = informe_tgr.generar(conexion_etl, id_archivo)

    assert nombre == "respuesta_tgr_01_resolucion_pdf_texto.xlsx"
    libro = load_workbook(io.BytesIO(contenido))
    filas = list(libro["Detalle"].iter_rows(min_row=2, values_only=True))
    assert len(filas) == 1
    rut, nombre_cliente, expediente, id_demanda, n_resol, _, deuda, saldo, descontado, pendiente, estado, *_ = filas[0]
    assert rut.replace(".", "") == esperado["rut"]
    assert (expediente, id_demanda, n_resol) == (esperado["expediente"], esperado["id_demanda"],
                                                 esperado["n_resolucion"])
    assert deuda == int(esperado["monto_solicitado"])
    assert estado == "Descontado" and descontado == deuda and pendiente == 0 and saldo >= deuda


def test_api_del_informe_a_la_tgr(conexion_etl, almacen):
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion_etl
    try:
        cliente = TestClient(app)
        sin_monto = recorrer(conexion_etl, almacen, "17_resolucion_sin_monto.xlsx")  # rechazada: no hay casos
        assert cliente.get(f"/api/reportes/informes/{sin_monto}/respuesta-tgr.xlsx").status_code == 409
        assert cliente.get("/api/reportes/informes/999999/respuesta-tgr.xlsx").status_code == 404

        core_bancario.cargar(conexion_etl, core_bancario.leer(CUENTAS), CUENTAS.name)
        servicio.fijar_utm(conexion_etl, servicio.periodo_de(datetime.now()), UTM)
        id_archivo = recorrer(conexion_etl, almacen, "12_resolucion_valida.xlsx")
        respuesta = cliente.get(f"/api/reportes/informes/{id_archivo}/respuesta-tgr.xlsx")

        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert "respuesta_tgr_12_resolucion_valida.xlsx" in respuesta.headers["content-disposition"]
        assert load_workbook(io.BytesIO(respuesta.content)).sheetnames == ["Resumen", "Detalle", "No procesados"]
    finally:
        app.dependency_overrides.clear()
