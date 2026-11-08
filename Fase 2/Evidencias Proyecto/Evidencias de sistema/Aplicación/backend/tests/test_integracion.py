"""Integración de punta a punta: los 22 documentos simulados recorren todo el flujo de un mes (RF01 a RF08, RF11).

Recepción → extracción (con OCR en escaneos, fotos y capturas) → ETL → cruce con el banco simulado → informe a la
TGR, avisos a clientes y panel. Se comprueba que cada documento termine donde dice el manifiesto y que los
números de los reportes coincidan entre sí.
"""
import io
from datetime import datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.modulos.cruce import core_bancario, servicio
from app.modulos.cruce.reglas import DESCONTADO, NO_DESCONTADO, PARCIAL, REVISION
from app.modulos.recepcion import WEB, procesar_pendientes, recibir_documento
from app.modulos.recepcion.registro import MotivoRechazo
from app.modulos.reportes import avisos, informe_tgr
from app.modulos.reportes.panel import indicadores
from tests.test_informe_tgr import CUENTAS, UTM
from tests.test_resoluciones import ARCHIVOS, DATOS, MB

SIN_ETL = {"17_resolucion_sin_monto.xlsx", "18_resolucion_sin_monto.docx", "19_resolucion_rut_invalido.csv"}


def nombre(entrada):
    return entrada["archivo"].rsplit("/", 1)[-1]


@pytest.fixture(scope="module")
def mes():
    """Todo el flujo corre una sola vez (el OCR tarda) y sus pruebas leen el resultado."""
    from sqlalchemy.exc import SQLAlchemyError

    from app.db import engine

    try:
        conexion = engine.connect()
    except SQLAlchemyError:
        pytest.skip("SQL Server no disponible")
    transaccion = conexion.begin()
    try:
        from tests.conftest import TABLAS_ETL

        if conexion.execute(text("SELECT COL_LENGTH('dbo.Archivos_TGR', 'hash_sha256')")).scalar_one() is None:
            pytest.skip("Falta ejecutar 'Base de datos/04_recepcion.sql'")
        for tabla in TABLAS_ETL:
            if conexion.execute(text("SELECT OBJECT_ID(:t, 'U')"), {"t": tabla}).scalar_one() is None:
                pytest.skip(f"Falta la tabla {tabla}")
            conexion.execute(text(f"DELETE FROM {tabla}"))
        for tabla in ("Analisis_IA_Anomalias", "Conciliacion_Banco", "Registros_TGR", "Archivos_TGR",
                      "Remitentes_Autorizados"):
            conexion.execute(text(f"DELETE FROM dbo.{tabla}"))

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as carpeta:
            almacen = Path(carpeta) / "almacen"
            core_bancario.cargar(conexion, core_bancario.leer(CUENTAS), CUENTAS.name)
            servicio.fijar_utm(conexion, servicio.periodo_de(datetime.now()), UTM)
            recibidos = {}
            for entrada in ARCHIVOS:
                ruta = DATOS / entrada["archivo"]
                recibidos[nombre(entrada)] = recibir_documento(conexion, ruta.read_bytes(), ruta.name, WEB,
                                                               almacen=almacen, tamano_maximo=20 * MB)
            procesar_pendientes(conexion, almacen, limite=50)
            yield conexion, recibidos
    finally:
        transaccion.rollback()
        conexion.close()


def test_la_recepcion_rechaza_reenvios_y_archivos_vacios(mes):
    _, recibidos = mes

    assert recibidos["03_resolucion_pdf_texto_reenvio.pdf"].motivo is MotivoRechazo.DUPLICADO
    assert recibidos["13_resolucion_valida_reenvio.xlsx"].motivo is MotivoRechazo.DUPLICADO
    assert recibidos["21_resolucion_vacia.csv"].motivo is MotivoRechazo.VACIO
    assert sum(r.aceptado for r in recibidos.values()) == 19


def estado(conexion, recibido):
    return conexion.execute(text("SELECT estado_archivo FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                            {"id": recibido.documento.id_archivo}).scalar_one()


def test_cada_documento_termina_en_el_estado_que_dice_el_manifiesto(mes):
    conexion, recibidos = mes

    for entrada in ARCHIVOS:
        recibido = recibidos[nombre(entrada)]
        if not recibido.aceptado:
            continue
        esperado = "Error de Extracción" if entrada["estado_extraccion_esperado"] == "Error de Extracción" else "Procesado"
        assert estado(conexion, recibido) == esperado, nombre(entrada)


def casos_cargados(conexion, recibido):
    return conexion.execute(text(
        "SELECT c.rut_limpio, c.dv_limpio, c.monto_solicitado, c.rev_manual_bit FROM core.casos_tgr c "
        "JOIN etl.resultados r ON r.id_caso = c.id_caso AND r.resultado = N'Cargado' "
        "JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion WHERE e.id_archivo = :id"),
        {"id": recibido.documento.id_archivo}).mappings().all()


def test_los_datos_cargados_coinciden_con_lo_esperado_en_todos_los_formatos(mes):
    conexion, recibidos = mes
    cargados = 0

    for entrada in ARCHIVOS:
        recibido = recibidos[nombre(entrada)]
        if not recibido.aceptado or entrada["estado_extraccion_esperado"] != "Normalizado" or nombre(entrada) in SIN_ETL:
            continue
        casos = casos_cargados(conexion, recibido)
        assert len(casos) == 1, nombre(entrada)
        esperado = entrada["deudor"]
        assert f"{casos[0]['rut_limpio']}-{casos[0]['dv_limpio']}" == esperado["rut"], nombre(entrada)
        assert str(int(casos[0]["monto_solicitado"])) == esperado["monto_solicitado"], nombre(entrada)
        assert bool(casos[0]["rev_manual_bit"]) == bool(entrada["requiere_revision_esperada"]), nombre(entrada)
        cargados += 1
    assert cargados == 13
    for archivo in SIN_ETL:
        assert casos_cargados(conexion, recibidos[archivo]) == []


def resultado_del_cruce(conexion, recibido):
    cruce = servicio.cruce_del_informe(conexion, recibido.documento.id_archivo)
    assert cruce is not None and len(cruce["resultados"]) == 1
    return cruce["resultados"][0]


def test_el_cruce_aplica_la_regla_de_descuento_segun_el_saldo_del_cliente(mes):
    conexion, recibidos = mes
    esperado_por_escenario = {"cubre": DESCONTADO, "parcial": PARCIAL, "sobre_media_utm": NO_DESCONTADO,
                              "sin_cuentas": NO_DESCONTADO}

    for entrada in ARCHIVOS:
        recibido = recibidos[nombre(entrada)]
        if not recibido.aceptado or entrada["estado_extraccion_esperado"] != "Normalizado" or nombre(entrada) in SIN_ETL:
            continue
        r = resultado_del_cruce(conexion, recibido)
        if entrada["requiere_revision_esperada"]:
            assert r["resultado"] == REVISION, nombre(entrada)  # un caso dudoso no se descuenta sin revisión
            continue
        assert r["resultado"] == esperado_por_escenario[entrada["escenario_banco"]], nombre(entrada)
        assert r["cliente"] == (entrada["escenario_banco"] != "sin_cuentas")
        if r["resultado"] == DESCONTADO:
            assert r["monto_descontado"] == r["monto_solicitado"] and r["monto_pendiente"] == 0
        if r["resultado"] == PARCIAL:
            assert 0 < r["monto_descontado"] < r["monto_solicitado"]
        if r["resultado"] == NO_DESCONTADO:
            assert r["monto_descontado"] == 0


def test_la_bandeja_junta_lo_que_necesita_revision_manual(mes):
    conexion, _ = mes

    pendientes = indicadores(conexion)["excepciones_pendientes"]

    assert pendientes["documento"] == 3  # PDF corrupto, Excel corrupto y archivo que no es una resolución
    assert pendientes["rechazo"] == 3  # sin monto (2) y RUT inválido
    assert pendientes["caso"] == 1  # la captura de baja resolución


def test_el_panel_el_informe_a_la_tgr_y_los_avisos_cuentan_lo_mismo(mes):
    conexion, recibidos = mes
    panel = indicadores(conexion)
    cruzados = [r for r in recibidos.values() if r.aceptado and servicio.cruce_del_informe(
        conexion, r.documento.id_archivo)]

    assert panel["informes"]["total"] == 19
    assert panel["casos"]["total"] == 13 and panel["cruce"]["informes"] == len(cruzados) == 13
    assert panel["cruce"]["descontados"] + panel["cruce"]["parciales"] + panel["cruce"]["no_descontados"] \
        + panel["cruce"]["en_revision"] == 13
    suma_descontado, con_aviso = Decimal(0), 0
    for recibido in cruzados:
        id_archivo = recibido.documento.id_archivo
        datos = informe_tgr.recopilar(conexion, id_archivo)
        total = informe_tgr.totales(datos)
        suma_descontado += total["monto_descontado"]
        lista = avisos.armar_avisos(datos["cruce"])
        con_aviso += len(lista)
        assert len(lista) == (1 if total["monto_descontado"] > 0 else 0)
        libro = load_workbook(io.BytesIO(informe_tgr.construir_excel(datos)))
        assert libro.sheetnames == ["Resumen", "Detalle", "No procesados"]
        assert len(list(libro["Detalle"].iter_rows(min_row=2))) == total["validos"] == 1
    assert suma_descontado == Decimal(str(panel["cruce"]["monto_descontado"]))
    assert con_aviso == panel["cruce"]["descontados"] + panel["cruce"]["parciales"]
