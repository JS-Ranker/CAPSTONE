"""Pruebas del generador de informes de deudores simulados: los archivos cumplen lo que dice el manifiesto."""
import csv
import hashlib
import json
import re

import pdfplumber
import pytest
from docx import Document
from openpyxl import load_workbook

from scripts.generar_datos_simulados import (
    CARGADO, COLUMNAS, DUPLICADO, RECHAZADO, REVISION, TITULOS, digito_verificador, generar,
)

_EXPEDIENTE = re.compile(r"^\d+-\d{4} .+$")


@pytest.fixture(scope="module")
def salida(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("simulados")
    generar(carpeta, semilla=2026)
    return carpeta


@pytest.fixture(scope="module")
def manifiesto(salida):
    return json.loads((salida / "manifiesto.json").read_text(encoding="utf-8"))


def entrada(manifiesto, nombre):
    return next(a for a in manifiesto["archivos"] if a["archivo"].endswith(nombre))


def rut_valido(rut):
    numero, _, dv = (rut or "").partition("-")
    return numero.isdigit() and dv != "" and digito_verificador(int(numero)) == dv.upper()


def huellas(carpeta):
    return {p.relative_to(carpeta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob("*")) if p.is_file()}


def test_misma_semilla_mismos_archivos(salida, tmp_path):
    otra = tmp_path / "otra"
    generar(otra, semilla=2026)
    assert huellas(otra) == huellas(salida)


def test_todos_los_archivos_del_manifiesto_existen(salida, manifiesto):
    for archivo in manifiesto["archivos"]:
        assert (salida / archivo["archivo"]).is_file(), archivo["archivo"]
    assert (salida / manifiesto["banco_generico"]["archivo"]).is_file()


def test_ruts_ficticios_en_el_rango_reservado(manifiesto):
    for archivo in manifiesto["archivos"]:
        for registro in archivo.get("registros", []):
            if rut_valido(registro["rut"]):
                assert 40_000_000 <= int(registro["rut"].split("-")[0]) <= 49_999_999


def test_deudores_cargados_tienen_los_datos_criticos_bien_formados(manifiesto):
    for archivo in manifiesto["archivos"]:
        for registro in archivo.get("registros", []):
            if registro["estado_esperado"] in (CARGADO, REVISION, DUPLICADO):
                assert rut_valido(registro["rut"]), registro
                assert isinstance(registro["monto_solicitado"], int) and registro["monto_solicitado"] > 0, registro
                assert _EXPEDIENTE.match(registro["expediente"]), registro


def test_los_casos_de_borde_cubren_cada_resultado(manifiesto):
    casos = entrada(manifiesto, "04_informe_casos_borde.xlsx")
    estados = {r["estado_esperado"] for r in casos["registros"]}
    assert estados == {CARGADO, RECHAZADO, REVISION, DUPLICADO}
    assert all(r.get("motivo") for r in casos["registros"] if r["estado_esperado"] != CARGADO)


def test_totales_declarados_cuadran_salvo_en_los_que_no_deben(manifiesto):
    for archivo in manifiesto["archivos"]:
        if "registros" not in archivo:
            continue
        suma = sum(r["monto_solicitado"] for r in archivo["registros"] if r["monto_solicitado"] is not None)
        cuadra = (archivo["suma_declarada"], archivo["cantidad_declarada"]) == (suma, len(archivo["registros"]))
        assert cuadra == ("no_cuadra" not in archivo["archivo"]), archivo["archivo"]


def test_excel_con_celdas_numericas_y_de_fecha(salida, manifiesto):
    hoja = load_workbook(salida / entrada(manifiesto, "01_informe_valido.xlsx")["archivo"]).active
    filas = list(hoja.iter_rows(values_only=True))
    titulos = filas.index(tuple(TITULOS[c] for c in COLUMNAS))
    primera = filas[titulos + 1]
    assert isinstance(primera[COLUMNAS.index("monto_solicitado")], int)
    assert primera[COLUMNAS.index("fecha_oficio")].year == 2026


def test_txt_en_latin1_separado_por_barra(salida, manifiesto):
    ruta = salida / entrada(manifiesto, "03_informe_latin1.txt")["archivo"]
    texto = ruta.read_bytes().decode("latin-1")
    with pytest.raises(UnicodeDecodeError):
        ruta.read_bytes().decode("utf-8")
    assert "|".join(TITULOS[c] for c in COLUMNAS) in texto


def test_csv_utf8_separado_por_punto_y_coma(salida, manifiesto):
    ruta = salida / entrada(manifiesto, "02_informe_valido.csv")["archivo"]
    with ruta.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.reader(archivo, delimiter=";"))
    assert [TITULOS[c] for c in COLUMNAS] in filas
    assert filas[-1][0] == "TOTALES"


def test_word_con_una_tabla_de_deudores(salida, manifiesto):
    esperado = entrada(manifiesto, "13_informe_valido.docx")
    documento = Document(str(salida / esperado["archivo"]))
    tabla = documento.tables[0]
    assert [c.text for c in tabla.rows[0].cells] == [TITULOS[c] for c in COLUMNAS]
    assert len(tabla.rows) - 1 == esperado["registros_en_detalle"]
    assert tabla.rows[1].cells[0].text.count(".") == 2          # RUT con puntos, como se imprime


def test_reenvio_es_copia_exacta(salida, manifiesto):
    original = (salida / entrada(manifiesto, "01_informe_valido.xlsx")["archivo"]).read_bytes()
    assert (salida / entrada(manifiesto, "12_informe_valido_reenvio.xlsx")["archivo"]).read_bytes() == original


def test_pdf_con_texto_seleccionable_y_escaneado_sin_texto(salida, manifiesto):
    with pdfplumber.open(salida / entrada(manifiesto, "21_informe_pdf_texto.pdf")["archivo"]) as pdf:
        assert "Informe de deudores" in pdf.pages[0].extract_text()
    with pdfplumber.open(salida / entrada(manifiesto, "23_informe_escaneado.pdf")["archivo"]) as pdf:
        assert not (pdf.pages[0].extract_text() or "").strip()


def test_cuentas_del_banco_solo_para_deudores_cargados(salida, manifiesto):
    with (salida / manifiesto["banco_generico"]["archivo"]).open(encoding="utf-8", newline="") as archivo:
        cuentas = list(csv.DictReader(archivo, delimiter=";"))
    assert len(cuentas) == manifiesto["banco_generico"]["cuentas"]
    assert all(rut_valido(c["rut_titular"]) and c["estado_cuenta"] == "Activa" for c in cuentas)
