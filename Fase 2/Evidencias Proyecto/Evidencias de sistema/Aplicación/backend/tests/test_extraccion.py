"""Pruebas del módulo de extracción (RF12, RN05) contra el manifiesto de los datos simulados."""
import csv
import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings
from app.modulos.extraccion import COLUMNAS_PLANTILLA, FormatoNoSoportado, escribir_plantilla, extraer
from app.modulos.extraccion.normalizacion import normalizar_fecha, normalizar_monto, normalizar_rut, rut_valido
from app.modulos.extraccion.plantilla import RegistroExtraido, ResultadoExtraccion
from scripts.generar_datos_simulados import COLUMNAS, Generador, dibujar_nomina, escribir_fotografia, generar

requiere_tesseract = pytest.mark.skipif(
    not (Path(settings.tesseract_cmd).is_file() or shutil.which(settings.tesseract_cmd)),
    reason="Tesseract no está instalado (TESSERACT_CMD en backend/.env)",
)


@pytest.fixture(scope="module")
def simulados(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("simulados")
    manifiesto = generar(carpeta, semilla=2026)
    esperados = {a["archivo"].rsplit("/", 1)[-1]: a for a in manifiesto["archivos"]}
    return carpeta / "no_estructurados", esperados


def como_texto(registro_esperado):
    """Valores del manifiesto tal como deben quedar en la plantilla (todo texto)."""
    return {c: "" if registro_esperado[c] is None else str(registro_esperado[c]) for c in COLUMNAS_PLANTILLA}


def test_la_plantilla_es_la_misma_que_usa_el_generador():
    assert COLUMNAS_PLANTILLA == COLUMNAS


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


def test_pdf_con_texto_se_extrae_igual_que_el_manifiesto(simulados):
    carpeta, esperados = simulados
    esperado = esperados["21_nomina_pdf_texto.pdf"]
    resultado = extraer(carpeta / "21_nomina_pdf_texto.pdf")

    assert resultado.estado == "Normalizado", resultado.errores
    assert resultado.tipo_documento == "PDF con texto"
    assert resultado.lote == esperado["lote"]
    assert resultado.fecha_documento == "2026-10-01"
    assert [r.valores for r in resultado.registros] == [como_texto(r) for r in esperado["registros"]]
    assert all(not r.requiere_revision for r in resultado.registros)
    assert resultado.confianza_promedio == 100.0


def test_pdf_con_totales_que_no_cuadran_va_a_revision_manual(simulados):
    carpeta, esperados = simulados
    resultado = extraer(carpeta / "22_nomina_pdf_texto_totales_no_cuadran.pdf")
    assert resultado.estado == esperados["22_nomina_pdf_texto_totales_no_cuadran.pdf"]["estado_archivo_esperado"]
    assert any("monto total" in error for error in resultado.errores)
    with pytest.raises(ValueError):
        escribir_plantilla(resultado, carpeta / "no_debe_escribirse.csv")


def test_escribir_plantilla(simulados, tmp_path):
    carpeta, esperados = simulados
    resultado = extraer(carpeta / "21_nomina_pdf_texto.pdf")
    destino = tmp_path / "normalizada.csv"
    escribir_plantilla(resultado, destino)

    with destino.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.reader(archivo, delimiter=";"))
    encabezado, columnas, detalle, pie = filas[0], filas[1], filas[2:-1], filas[-1]
    esperado = esperados["21_nomina_pdf_texto.pdf"]
    assert encabezado == ["ENCABEZADO", "TGR", esperado["lote"], "2026-10-01", "25"]
    assert tuple(columnas) == COLUMNAS_PLANTILLA
    assert len(detalle) == 25
    assert pie == ["TOTALES", "25", str(esperado["suma_declarada"])]


def test_registro_con_campo_critico_poco_confiable_requiere_revision():
    confianzas = {c: 99.0 for c in COLUMNAS_PLANTILLA} | {"monto": 72.0}
    registro = RegistroExtraido({c: "" for c in COLUMNAS_PLANTILLA}, confianzas)
    assert registro.confianza == 72.0
    assert registro.requiere_revision
    # La confianza de un campo no crítico no afecta (RN05: RUT, monto y cuenta).
    confianzas = {c: 99.0 for c in COLUMNAS_PLANTILLA} | {"nombre_deudor": 10.0}
    assert not RegistroExtraido({}, confianzas).requiere_revision


def test_documento_sin_totales_no_se_rechaza_pero_queda_anotado():
    resultado = ResultadoExtraccion(tipo_documento="PDF con texto")
    resultado.verificar_totales()
    assert resultado.estado == "Normalizado"
    assert resultado.observaciones


def test_formato_estructurado_no_corresponde_a_extraccion(tmp_path):
    ruta = tmp_path / "nomina.xlsx"
    ruta.write_bytes(b"")
    with pytest.raises(FormatoNoSoportado):
        extraer(ruta)


@pytest.mark.parametrize("rut, valido", [("12345678-5", True), ("10000013-K", True), ("12345678-4", False), ("", False)])
def test_rut_valido(rut, valido):
    assert rut_valido(rut) is valido


# ------------------------------------------------------------------ OCR de PDF escaneados (etapa 2)


def escanear(tmp_path, nomina, angulo):
    """Guarda la nómina como PDF de solo imagen, girada `angulo` grados."""
    hoja, _ = dibujar_nomina(nomina)
    hoja = hoja.convert("L").rotate(angulo, resample=Image.Resampling.BICUBIC, fillcolor=255)
    ruta = tmp_path / f"escaneo_{angulo}.pdf"
    hoja.save(ruta, "PDF", resolution=200.0)
    return ruta


@requiere_tesseract
def test_pdf_escaneado_se_extrae_igual_que_el_manifiesto(simulados):
    carpeta, esperados = simulados
    esperado = esperados["23_nomina_escaneada.pdf"]
    resultado = extraer(carpeta / "23_nomina_escaneada.pdf")

    assert resultado.estado == "Normalizado", resultado.errores
    assert resultado.tipo_documento == "PDF escaneado"
    assert resultado.lote == esperado["lote"]
    assert (resultado.cantidad_declarada, resultado.suma_declarada) == (25, esperado["suma_declarada"])
    assert [r.valores for r in resultado.registros] == [como_texto(r) for r in esperado["registros"]]
    assert not any(r.requiere_revision for r in resultado.registros)


@requiere_tesseract
@pytest.mark.parametrize("angulo", [2.5, -3.0])
def test_escaneo_torcido_se_endereza(tmp_path, angulo):
    nomina = Generador(semilla=5).nomina(12)
    resultado = extraer(escanear(tmp_path, nomina, angulo))
    assert resultado.estado == "Normalizado", resultado.errores
    leidos = [(r.valores["rut_deudor"], r.valores["monto"], r.valores["cuenta_destino"]) for r in resultado.registros]
    assert leidos == [(r.rut, str(r.monto), r.cuenta) for r in nomina.registros]


@requiere_tesseract
def test_escaneo_con_totales_que_no_cuadran_va_a_revision_manual(tmp_path):
    nomina = Generador(semilla=6).nomina(10)
    nomina.suma_declarada = nomina.suma + 10_000
    resultado = extraer(escanear(tmp_path, nomina, 0.4))
    assert resultado.estado == "Error de Extracción"
    assert any("monto total" in error for error in resultado.errores)


@requiere_tesseract
def test_imagen_sin_tabla_se_rechaza(tmp_path):
    ruta = tmp_path / "en_blanco.pdf"
    Image.new("L", (1654, 2339), 255).save(ruta, "PDF", resolution=200.0)
    resultado = extraer(ruta)
    assert resultado.estado == "Error de Extracción"
    assert not resultado.registros


# ------------------------------------------------------------------ OCR de fotografías (etapa 3)


def criticos(valores):
    return valores["rut_deudor"], valores["monto"], valores["cuenta_destino"]


def criticos_esperados(registro):
    return registro.rut, str(registro.monto), registro.cuenta


@requiere_tesseract
def test_foto_manchada_no_acepta_ningun_valor_dudoso(simulados):
    """RN05: lo que no va a revisión debe estar bien leído, y los montos manchados van a revisión."""
    carpeta, esperados = simulados
    esperado = esperados["24_foto_nomina.jpg"]
    resultado = extraer(carpeta / "24_foto_nomina.jpg")

    assert resultado.tipo_documento == "Imagen"
    assert len(resultado.registros) == 25
    assert resultado.estado == esperado["estado_archivo_esperado"]  # CU12 5b: los totales no cuadran
    for extraido, registro in zip(resultado.registros, esperado["registros"]):
        if registro["estado_esperado"] == "Revisión de Extracción":
            assert extraido.requiere_revision, registro["id_transaccion"]
        if not extraido.requiere_revision:
            assert extraido.valores == como_texto(registro), registro["id_transaccion"]
    aceptados = sum(not r.requiere_revision for r in resultado.registros)
    assert aceptados >= 10, f"solo {aceptados} de 25 registros se aceptaron sin revisión"


@requiere_tesseract
def test_foto_sin_manchas(tmp_path):
    nomina = Generador(semilla=11).nomina(20)
    ruta = tmp_path / "foto.jpg"
    escribir_fotografia(ruta, nomina, filas_manchadas=[])
    resultado = extraer(ruta)
    assert resultado.estado == "Normalizado", resultado.errores
    assert [criticos(r.valores) for r in resultado.registros] == [criticos_esperados(r) for r in nomina.registros]


@requiere_tesseract
def test_foto_ya_recortada_sin_fondo(tmp_path):
    nomina = Generador(semilla=12).nomina(20)
    hoja, _ = dibujar_nomina(nomina)
    ruta = tmp_path / "recortada.jpg"
    hoja.save(ruta, quality=80)
    resultado = extraer(ruta)
    assert resultado.estado == "Normalizado", resultado.errores
    assert (resultado.cantidad_declarada, resultado.suma_declarada) == (20, nomina.suma)
    assert [criticos(r.valores) for r in resultado.registros] == [criticos_esperados(r) for r in nomina.registros]


@requiere_tesseract
def test_foto_de_celular_girada_con_orientacion_exif(tmp_path):
    nomina = Generador(semilla=13).nomina(20)
    original = tmp_path / "original.jpg"
    escribir_fotografia(original, nomina, filas_manchadas=[])
    girada = tmp_path / "girada.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: el visor debe girarla 90° a la derecha
    Image.open(original).rotate(90, expand=True).save(girada, exif=exif, quality=85)
    resultado = extraer(girada)
    assert [criticos(r.valores) for r in resultado.registros] == [criticos_esperados(r) for r in nomina.registros]
