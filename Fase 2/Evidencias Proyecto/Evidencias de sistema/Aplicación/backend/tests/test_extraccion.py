"""Pruebas de la extracción de informes de deudores (RF02, RF12, RN04, RN05) contra el manifiesto simulado."""
import csv
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings
from app.modulos.etl.desde_informe import campos_dudosos, filas_para_etl
from app.modulos.etl.reglas import COLUMNAS_STG
from app.modulos.extraccion import COLUMNAS_PLANTILLA, FormatoNoSoportado, escribir_plantilla, extraer
from app.modulos.extraccion.normalizacion import normalizar_fecha, normalizar_monto, normalizar_rut, rut_valido
from app.modulos.extraccion.plantilla import CAMPOS_CRITICOS, RegistroExtraido, ResultadoExtraccion
from scripts.generar_datos_simulados import (
    COLUMNAS, REVISION, Generador, dibujar_informe, escribir_fotografia, generar,
)

requiere_tesseract = pytest.mark.skipif(
    not (Path(settings.tesseract_cmd).is_file() or shutil.which(settings.tesseract_cmd)),
    reason="Tesseract no está instalado (TESSERACT_CMD en backend/.env)",
)


@pytest.fixture(scope="module")
def simulados(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("simulados")
    manifiesto = generar(carpeta, semilla=2026)
    return carpeta, {a["archivo"].rsplit("/", 1)[-1]: a for a in manifiesto["archivos"]}


def archivo(simulados, nombre):
    carpeta, esperados = simulados
    esperado = esperados[nombre]
    return carpeta / esperado["archivo"], esperado


def como_texto(registro_esperado):
    """Valores del manifiesto tal como los entrega la extracción (todo texto, normalizado).

    Un valor que no se puede normalizar ("mil pesos", "31-02-2026") llega tal como está en el archivo,
    para que el ETL lo rechace con su motivo.
    """
    en_archivo = registro_esperado.get("valor_en_archivo", {})
    valores = {}
    for c in COLUMNAS_PLANTILLA:
        if registro_esperado[c] is None:
            valores[c] = en_archivo.get(c, "").strip()
        else:
            valores[c] = str(registro_esperado[c])
    return valores


def criticos(valores):
    return tuple(valores[c] for c in CAMPOS_CRITICOS)


def criticos_esperados(registro):
    return registro.rut, str(registro.monto), registro.expediente


def test_las_columnas_son_las_mismas_que_usa_el_generador():
    assert COLUMNAS_PLANTILLA == COLUMNAS


# ------------------------------------------------------------------ normalización

@pytest.mark.parametrize("texto, esperado", [
    ("12.345.678-5", "12345678-5"),
    ("  10000013-k ", "10000013-K"),
    ("12345678 5", "12345678-5"),
    ("12A45678-5", "12A45678-5"),  # no se puede normalizar: queda para la validación
    ("", ""),
])
def test_normalizar_rut(texto, esperado):
    assert normalizar_rut(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("$ 1.250.000", "1250000"), ("1250000", "1250000"), ("$1.250.000", "1250000"), ("mil pesos", "mil pesos"),
])
def test_normalizar_monto(texto, esperado):
    assert normalizar_monto(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("15-09-2026", "2026-09-15"), ("15/09/2026", "2026-09-15"), ("2026-09-15", "2026-09-15"),
    ("31-02-2026", "31-02-2026"),
])
def test_normalizar_fecha(texto, esperado):
    assert normalizar_fecha(texto) == esperado


@pytest.mark.parametrize("rut, valido", [("12345678-5", True), ("10000013-K", True), ("12345678-4", False), ("", False)])
def test_rut_valido(rut, valido):
    assert rut_valido(rut) is valido


def test_registro_con_campo_critico_poco_confiable_requiere_revision():
    confianzas = {c: 99.0 for c in COLUMNAS_PLANTILLA} | {"monto_solicitado": 72.0}
    registro = RegistroExtraido({c: "" for c in COLUMNAS_PLANTILLA}, confianzas)
    assert registro.confianza == 72.0
    assert registro.requiere_revision
    # La confianza de un campo no crítico no afecta (RN05: RUT, monto y expediente).
    confianzas = {c: 99.0 for c in COLUMNAS_PLANTILLA} | {"tesoreria": 10.0}
    assert not RegistroExtraido({}, confianzas).requiere_revision


def test_documento_sin_totales_no_se_rechaza_pero_queda_anotado():
    resultado = ResultadoExtraccion(tipo_documento="PDF con texto")
    resultado.verificar_totales()
    assert resultado.estado == "Normalizado"
    assert resultado.observaciones


def test_formato_desconocido(tmp_path):
    ruta = tmp_path / "informe.odt"
    ruta.write_bytes(b"")
    with pytest.raises(FormatoNoSoportado):
        extraer(ruta)


def test_excel_antiguo_explica_que_hacer(tmp_path):
    ruta = tmp_path / "informe.xls"
    ruta.write_bytes(b"\xd0\xcf\x11\xe0")
    resultado = extraer(ruta)
    assert resultado.estado == "Error de Extracción"
    assert ".xlsx" in resultado.errores[0]


# ------------------------------------------------------------------ formatos estructurados (sin OCR)

@pytest.mark.parametrize("nombre, tipo", [
    ("01_informe_valido.xlsx", "Excel"),
    ("02_informe_valido.csv", "CSV"),
    ("03_informe_latin1.txt", "TXT"),            # ISO-8859-1 separado por |
    ("04_informe_casos_borde.xlsx", "Excel"),
    ("08_informe_sin_totales.csv", "CSV"),
    ("13_informe_valido.docx", "Word"),          # RUT con puntos y montos en pesos
])
def test_informe_estructurado_se_extrae_igual_que_el_manifiesto(simulados, nombre, tipo):
    ruta, esperado = archivo(simulados, nombre)
    resultado = extraer(ruta)

    assert resultado.estado == "Normalizado", resultado.errores
    assert resultado.tipo_documento == tipo
    assert resultado.lote == esperado["lote"]
    assert [r.valores for r in resultado.registros] == [como_texto(r) for r in esperado["registros"]]
    assert resultado.confianza_promedio == 100.0


def test_informe_sin_totales_verifica_solo_la_cantidad_del_encabezado(simulados):
    ruta, _ = archivo(simulados, "08_informe_sin_totales.csv")
    resultado = extraer(ruta)
    assert (resultado.cantidad_declarada, resultado.suma_declarada) == (30, None)
    assert not resultado.errores


@pytest.mark.parametrize("nombre, error", [
    ("06_informe_totales_no_cuadran.csv", "monto total"),
    ("07_informe_cantidad_no_cuadra.xlsx", "declara 43 registros"),
    ("09_informe_columnas_incorrectas.csv", "fila de títulos"),
    ("10_informe_corrupto.xlsx", "dañado"),
    ("11_informe_vacio.csv", "no trae deudores"),
])
def test_informe_estructurado_con_error_va_a_revision_manual(simulados, nombre, error):
    ruta, esperado = archivo(simulados, nombre)
    resultado = extraer(ruta)
    assert resultado.estado == esperado["estado_archivo_esperado"] == "Error de Extracción"
    assert any(error in e for e in resultado.errores), resultado.errores


# ------------------------------------------------------------------ PDF con texto

def test_pdf_con_texto_se_extrae_igual_que_el_manifiesto(simulados):
    ruta, esperado = archivo(simulados, "21_informe_pdf_texto.pdf")
    resultado = extraer(ruta)

    assert resultado.estado == "Normalizado", resultado.errores
    assert resultado.tipo_documento == "PDF con texto"
    assert resultado.lote == esperado["lote"]
    assert resultado.fecha_documento == "2026-10-01"
    assert [r.valores for r in resultado.registros] == [como_texto(r) for r in esperado["registros"]]
    assert all(not r.requiere_revision for r in resultado.registros)


def test_pdf_con_totales_que_no_cuadran_va_a_revision_manual(simulados, tmp_path):
    ruta, esperado = archivo(simulados, "22_informe_pdf_texto_totales_no_cuadran.pdf")
    resultado = extraer(ruta)
    assert resultado.estado == esperado["estado_archivo_esperado"]
    assert any("monto total" in error for error in resultado.errores)
    with pytest.raises(ValueError):
        escribir_plantilla(resultado, tmp_path / "no_debe_escribirse.csv")


def test_escribir_plantilla(simulados, tmp_path):
    ruta, esperado = archivo(simulados, "21_informe_pdf_texto.pdf")
    destino = tmp_path / "normalizada.csv"
    escribir_plantilla(extraer(ruta), destino)

    with destino.open(encoding="utf-8", newline="") as salida:
        filas = list(csv.reader(salida, delimiter=";"))
    encabezado, columnas, detalle, pie = filas[0], filas[1], filas[2:-1], filas[-1]
    assert encabezado == ["ENCABEZADO", "TGR", esperado["lote"], "2026-10-01", "25"]
    assert tuple(columnas) == COLUMNAS_PLANTILLA
    assert len(detalle) == 25
    assert pie == ["TOTALES", "25", str(esperado["suma_declarada"])]


# ------------------------------------------------------------------ de la extracción al ETL

def resultado_de(*valores_y_confianzas):
    resultado = ResultadoExtraccion(tipo_documento="Imagen")
    for valores, confianzas in valores_y_confianzas:
        resultado.registros.append(RegistroExtraido(valores, confianzas))
    return resultado


def deudor(**cambios):
    valores = {
        "rut": "46822128-4", "nombre": "Francisco Muñoz Díaz", "id_demanda": "689183", "n_resolucion": "79612",
        "monto_solicitado": "403000", "tipo_embargo": "RETENCIÓN", "expediente": "30237-2022 SANTIAGO",
        "tesoreria": "TESORERÍA REGIONAL DE SANTIAGO", "fecha_oficio": "2026-09-28",
    }
    return {**valores, **cambios}, {c: 100.0 for c in COLUMNAS_PLANTILLA}


def test_filas_para_etl_completa_las_columnas_del_proceso():
    resultado = resultado_de(deudor())
    fila = filas_para_etl(resultado, nombre_archivo="informe.pdf", fecha_recepcion=datetime(2026, 10, 12, 9, 30),
                          remitente="nominas@tgr.cl", asunto="Informe octubre")[0]

    assert list(fila) == list(COLUMNAS_STG)
    assert (fila["rut"], fila["dv"]) == ("46822128", "4")
    assert fila["fecha_oficio"] == "28-09-2026"                 # el ETL espera dd-mm-aaaa
    assert (fila["fec_ing"], fila["nombre_documento"]) == ("12-10-2026", "20261012")
    assert (fila["rol"], fila["n_resol"], fila["nom_cli"]) == ("30237-2022 SANTIAGO", "79612", "Francisco Muñoz Díaz")
    assert (fila["mult_rol"], fila["rev_manual"], fila["camp_falt"]) == ("NO", "NO", "")
    assert (fila["remit"], fila["asunto"], fila["ruta_doc"]) == ("nominas@tgr.cl", "Informe octubre", "informe.pdf")
    assert fila["saldo_menor_05_utm"] == ""                   # lo decide el cruce, no el informe


def test_mismo_rut_dos_veces_es_multiples_roles():
    resultado = resultado_de(deudor(), deudor(expediente="555-2025 SANTIAGO"), deudor(rut="41346427-7"))
    filas = filas_para_etl(resultado, nombre_archivo="x", fecha_recepcion=datetime(2026, 10, 12))
    assert [f["mult_rol"] for f in filas] == ["SI", "SI", "NO"]


def test_revision_manual_por_dato_vacio_o_critico_dudoso():
    valores, confianzas = deudor(fecha_oficio="")
    assert campos_dudosos(valores, confianzas) == ["FECHA OFICIO"]
    valores, confianzas = deudor()
    assert campos_dudosos(valores, confianzas | {"monto_solicitado": 80.0}) == ["MONTO SOLICITADO"]
    assert campos_dudosos(valores, confianzas | {"tesoreria": 40.0}) == []   # no crítico: no se revisa

    resultado = resultado_de(deudor(n_resolucion=""))
    fila = filas_para_etl(resultado, nombre_archivo="x", fecha_recepcion=datetime(2026, 10, 12))[0]
    assert (fila["rev_manual"], fila["camp_falt"]) == ("SI", "N° RESOLUCIÓN")


def test_rut_ilegible_queda_tal_cual_para_que_el_etl_lo_rechace():
    fila = filas_para_etl(resultado_de(deudor(rut="12A45678-5")), nombre_archivo="x",
                          fecha_recepcion=datetime(2026, 10, 12))[0]
    assert (fila["rut"], fila["dv"]) == ("12A45678-5", "")


# ------------------------------------------------------------------ OCR de PDF escaneados


def escanear(tmp_path, informe, angulo):
    """Guarda el informe como PDF de solo imagen, girado `angulo` grados."""
    hoja, _ = dibujar_informe(informe)
    hoja = hoja.convert("L").rotate(angulo, resample=Image.Resampling.BICUBIC, fillcolor=255)
    ruta = tmp_path / f"escaneo_{angulo}.pdf"
    hoja.save(ruta, "PDF", resolution=200.0)
    return ruta


def assert_ningun_critico_mal_aceptado(resultado, esperados, minimo_aceptados):
    """RN05: lo que no va a revisión debe estar bien leído; y la mayoría debe poder aceptarse."""
    assert len(resultado.registros) == len(esperados)
    for extraido, esperado in zip(resultado.registros, esperados):
        if not extraido.requiere_revision:
            assert criticos(extraido.valores) == esperado, esperado
    aceptados = sum(not r.requiere_revision for r in resultado.registros)
    assert aceptados >= minimo_aceptados, f"solo {aceptados} de {len(esperados)} se aceptaron sin revisión"


@requiere_tesseract
def test_pdf_escaneado(simulados):
    ruta, esperado = archivo(simulados, "23_informe_escaneado.pdf")
    resultado = extraer(ruta)

    assert resultado.estado == "Normalizado", resultado.errores
    assert resultado.tipo_documento == "PDF escaneado"
    assert resultado.lote == esperado["lote"]
    assert (resultado.cantidad_declarada, resultado.suma_declarada) == (25, esperado["suma_declarada"])
    for extraido, registro in zip(resultado.registros, esperado["registros"]):
        if not extraido.requiere_revision:
            assert extraido.valores == como_texto(registro), registro["rut"]
    assert sum(not r.requiere_revision for r in resultado.registros) >= 20


@requiere_tesseract
@pytest.mark.parametrize("angulo", [2.5, -3.0])
def test_escaneo_torcido_se_endereza(tmp_path, angulo):
    informe = Generador(semilla=5).informe(12)
    resultado = extraer(escanear(tmp_path, informe, angulo))
    assert resultado.estado == "Normalizado", resultado.errores
    assert_ningun_critico_mal_aceptado(resultado, [criticos_esperados(r) for r in informe.registros], 9)


@requiere_tesseract
def test_escaneo_con_totales_que_no_cuadran_va_a_revision_manual(tmp_path):
    informe = Generador(semilla=6).informe(10)
    informe.suma_declarada = informe.suma + 10_000
    resultado = extraer(escanear(tmp_path, informe, 0.4))
    assert resultado.estado == "Error de Extracción"
    assert any("monto total" in error for error in resultado.errores)


@requiere_tesseract
def test_imagen_sin_tabla_se_rechaza(tmp_path):
    ruta = tmp_path / "en_blanco.pdf"
    Image.new("L", (1654, 2339), 255).save(ruta, "PDF", resolution=200.0)
    resultado = extraer(ruta)
    assert resultado.estado == "Error de Extracción"
    assert not resultado.registros


# ------------------------------------------------------------------ OCR de fotografías


@requiere_tesseract
def test_foto_manchada_no_acepta_ningun_valor_dudoso(simulados):
    """RN05: los montos manchados van a revisión y lo que se acepta está bien leído."""
    ruta, esperado = archivo(simulados, "24_foto_informe.jpg")
    resultado = extraer(ruta)

    assert resultado.tipo_documento == "Imagen"
    assert resultado.estado == esperado["estado_archivo_esperado"]  # CU12 5b: los totales no cuadran
    for extraido, registro in zip(resultado.registros, esperado["registros"]):
        if registro["estado_esperado"] == REVISION:
            assert extraido.requiere_revision, registro["rut"]
    criticos_manifiesto = [(r["rut"], str(r["monto_solicitado"]), r["expediente"]) for r in esperado["registros"]]
    assert_ningun_critico_mal_aceptado(resultado, criticos_manifiesto, 10)


@requiere_tesseract
def test_foto_sin_manchas(tmp_path):
    informe = Generador(semilla=11).informe(20)
    ruta = tmp_path / "foto.jpg"
    escribir_fotografia(ruta, informe, filas_manchadas=[])
    resultado = extraer(ruta)
    assert_ningun_critico_mal_aceptado(resultado, [criticos_esperados(r) for r in informe.registros], 12)


@requiere_tesseract
def test_foto_ya_recortada_sin_fondo(tmp_path):
    informe = Generador(semilla=12).informe(20)
    hoja, _ = dibujar_informe(informe)
    ruta = tmp_path / "recortada.jpg"
    hoja.save(ruta, quality=80)
    resultado = extraer(ruta)
    assert (resultado.cantidad_declarada, resultado.suma_declarada) == (20, informe.suma)
    assert_ningun_critico_mal_aceptado(resultado, [criticos_esperados(r) for r in informe.registros], 15)


@requiere_tesseract
def test_foto_de_celular_girada_con_orientacion_exif(tmp_path):
    informe = Generador(semilla=13).informe(20)
    original = tmp_path / "original.jpg"
    escribir_fotografia(original, informe, filas_manchadas=[])
    girada = tmp_path / "girada.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: el visor debe girarla 90° a la derecha
    Image.open(original).rotate(90, expand=True).save(girada, exif=exif, quality=85)
    resultado = extraer(girada)
    assert_ningun_critico_mal_aceptado(resultado, [criticos_esperados(r) for r in informe.registros], 12)
