"""Pruebas de las resoluciones de la TGR (un deudor por documento) de data/simulados en todos sus formatos.

La extracción lee cada archivo y el resultado se compara con el manifiesto que escribe
scripts/generar_datos_simulados.py. Con SQL Server, además, cada documento recorre recepción, extracción y ETL.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import BACKEND_DIR
from app.modulos.extraccion import extraer
from app.modulos.recepcion import WEB, procesar_pendientes, recibir_documento
from scripts.generar_datos_simulados import generar

DATOS = BACKEND_DIR.parent / "data" / "simulados"
MANIFIESTO = json.loads((DATOS / "manifiesto.json").read_text(encoding="utf-8"))
ARCHIVOS = MANIFIESTO["archivos"]
CRITICOS = ("rut", "monto_solicitado", "expediente")
MB = 1024 * 1024


def ids(archivos):
    return [Path(a["archivo"]).name for a in archivos]


def por_nombre(nombre):
    return next(a for a in ARCHIVOS if a["archivo"].endswith(nombre))


@pytest.fixture(scope="module")
def regenerado(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("simulados")
    return generar(carpeta, semilla=MANIFIESTO["semilla"])


def test_los_ejemplos_versionados_son_los_que_genera_el_script(regenerado):
    assert regenerado == MANIFIESTO


def test_hay_un_ejemplo_de_cada_formato_y_de_cada_problema():
    formatos = {a["formato"] for a in ARCHIVOS}
    assert formatos == {"PDF con texto", "PDF escaneado", "Imagen", "Excel", "CSV", "TXT", "Word"}
    assert {Path(a["archivo"]).suffix for a in ARCHIVOS} >= {".pdf", ".jpg", ".png", ".xlsx", ".csv", ".txt", ".docx"}
    assert any(a["duplicado_de"] for a in ARCHIVOS)
    assert sum(a["estado_extraccion_esperado"] == "Error de Extracción" for a in ARCHIVOS) >= 4
    for a in ARCHIVOS:
        assert (DATOS / a["archivo"]).is_file()


@pytest.mark.parametrize("entrada", [a for a in ARCHIVOS if not a["lee_con_ocr"]], ids=ids([a for a in ARCHIVOS if not a["lee_con_ocr"]]))
def test_los_formatos_de_texto_se_leen_exactamente(entrada):
    resultado = extraer(DATOS / entrada["archivo"])

    assert resultado.estado == entrada["estado_extraccion_esperado"]
    if resultado.estado != "Normalizado":
        assert resultado.errores and not resultado.registros
        return
    assert len(resultado.registros) == 1  # una resolución, un deudor
    registro = resultado.registros[0]
    assert registro.valores == entrada["deudor"]
    assert registro.requiere_revision == entrada["requiere_revision_esperada"]
    assert resultado.tipo_documento == entrada["formato"]


@pytest.mark.parametrize("entrada", [a for a in ARCHIVOS if a["lee_con_ocr"]], ids=ids([a for a in ARCHIVOS if a["lee_con_ocr"]]))
def test_el_ocr_lee_los_datos_criticos_de_escaneos_fotos_y_capturas(entrada):
    resultado = extraer(DATOS / entrada["archivo"])

    assert resultado.estado == "Normalizado"
    assert resultado.tipo_documento == entrada["formato"]
    registro = resultado.registros[0]
    for campo in CRITICOS:
        assert registro.valores[campo] == entrada["deudor"][campo], campo
    assert registro.requiere_revision == entrada["requiere_revision_esperada"]


def test_un_documento_sin_datos_de_resolucion_va_a_revision_manual():
    resultado = extraer(DATOS / por_nombre("22_informe_otro_formato.csv")["archivo"])

    assert resultado.estado == "Error de Extracción"


def test_el_reenvio_es_identico_al_original():
    for entrada in (a for a in ARCHIVOS if a["duplicado_de"]):
        assert (DATOS / entrada["archivo"]).read_bytes() == (DATOS / entrada["duplicado_de"]).read_bytes()


def test_los_rut_simulados_no_son_de_personas_reales():
    for entrada in ARCHIVOS:
        if entrada["deudor"]:
            numero = int(entrada["deudor"]["rut"].split("-")[0])
            assert 40_000_000 <= numero <= 49_999_999


def recorrer(conexion, almacen, nombre):
    ruta = DATOS / por_nombre(nombre)["archivo"]
    recibido = recibir_documento(conexion, ruta.read_bytes(), ruta.name, WEB, almacen=almacen, tamano_maximo=20 * MB)
    procesar_pendientes(conexion, almacen)
    return recibido.documento.id_archivo


def caso(conexion, id_archivo):
    return conexion.execute(text(
        "SELECT c.rut_limpio, c.dv_limpio, c.id_demanda, c.n_resol, c.monto_solicitado, c.rol, c.rev_manual_bit "
        "FROM core.casos_tgr c JOIN etl.resultados r ON r.id_caso = c.id_caso AND r.resultado = N'Cargado' "
        "JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion WHERE e.id_archivo = :id"),
        {"id": id_archivo}).mappings().all()


@pytest.mark.parametrize("nombre", ["01_resolucion_pdf_texto.pdf", "12_resolucion_valida.xlsx",
                                    "14_resolucion_valida.csv", "15_resolucion_valida.docx",
                                    "16_resolucion_latin1.txt"])
def test_una_resolucion_valida_queda_cargada_como_caso(conexion_etl, almacen, nombre):
    id_archivo = recorrer(conexion_etl, almacen, nombre)
    esperado = por_nombre(nombre)["deudor"]

    estado = conexion_etl.execute(text("SELECT estado_archivo FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                                  {"id": id_archivo}).scalar_one()
    casos = caso(conexion_etl, id_archivo)
    assert estado == "Procesado"
    assert len(casos) == 1
    fila = casos[0]
    assert f"{fila['rut_limpio']}-{fila['dv_limpio']}" == esperado["rut"]
    assert (str(fila["id_demanda"]), str(fila["n_resol"]), str(int(fila["monto_solicitado"]))) == (
        esperado["id_demanda"], esperado["n_resolucion"], esperado["monto_solicitado"])
    assert not fila["rev_manual_bit"]


@pytest.mark.parametrize("nombre", ["17_resolucion_sin_monto.xlsx", "18_resolucion_sin_monto.docx"])
def test_una_resolucion_sin_monto_es_rechazada_y_queda_en_la_bandeja(conexion_etl, almacen, nombre):
    id_archivo = recorrer(conexion_etl, almacen, nombre)

    assert caso(conexion_etl, id_archivo) == []
    filas = conexion_etl.execute(text(
        "SELECT r.resultado, r.motivo FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
        "WHERE e.id_archivo = :id"), {"id": id_archivo}).all()
    assert [f.resultado for f in filas] == ["Rechazado"]
    assert "monto" in filas[0].motivo.lower()


def test_una_resolucion_con_rut_invalido_es_rechazada_por_el_etl(conexion_etl, almacen):
    id_archivo = recorrer(conexion_etl, almacen, "19_resolucion_rut_invalido.csv")

    assert caso(conexion_etl, id_archivo) == []
    motivos = conexion_etl.execute(text(
        "SELECT r.resultado FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
        "WHERE e.id_archivo = :id"), {"id": id_archivo}).scalars().all()
    assert motivos == ["Rechazado"]
