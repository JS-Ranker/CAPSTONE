"""Pruebas del módulo de recepción (RF01, RN02, CU02) con los datos simulados y SQL Server."""
import json

import pytest
from sqlalchemy import text

from app.modulos.recepcion.registro import (
    CORREO, SFTP, WEB, MotivoRechazo, DatosCorreo, nombre_seguro, recibir_documento,
)
from tests.conftest import simulado

MB = 1024 * 1024


def recibir(conexion, almacen, nombre_simulado, canal=WEB, nombre=None, **opciones):
    ruta = simulado(nombre_simulado)
    return recibir_documento(conexion, ruta.read_bytes(), nombre or ruta.name, canal,
                             almacen=almacen, tamano_maximo=opciones.pop("tamano_maximo", 20 * MB), **opciones)


def fila(conexion, id_archivo):
    return conexion.execute(text("SELECT * FROM dbo.Archivos_TGR WHERE id_archivo = :id"), {"id": id_archivo}).mappings().one()


def ultima_bitacora(conexion):
    accion, detalle = conexion.execute(text(
        "SELECT TOP 1 accion_ejecutada, detalle_cambio FROM dbo.Bitacora_Trazabilidad ORDER BY id_bitacora DESC"
    )).one()
    return accion, json.loads(detalle)


def contar_archivos(conexion):
    return conexion.execute(text("SELECT COUNT(*) FROM dbo.Archivos_TGR")).scalar_one()


@pytest.mark.parametrize("nombre, esperado", [
    ("01_informe_valido.xlsx", "01_informe_valido.xlsx"),
    ("../../etc/passwd.csv", "passwd.csv"),
    ("C:\\Users\\tgr\\nómina 01.xlsx", "nómina 01.xlsx"),
    ('nómina<>:"|?*.csv', "nómina_______.csv"),
    ("   ", "documento"),
    ("a" * 300 + ".pdf", "a" * 146 + ".pdf"),
])
def test_nombre_seguro(nombre, esperado):
    assert nombre_seguro(nombre) == esperado


def test_registra_un_excel_valido(conexion, almacen):
    resultado = recibir(conexion, almacen, "01_informe_valido.xlsx")

    assert resultado.aceptado
    documento = resultado.documento
    assert (documento.tipo_documento, documento.estado_archivo, documento.canal_origen) == ("Excel", "Pendiente de Extracción", "Web")
    registro = fila(conexion, documento.id_archivo)
    assert registro["hash_sha256"] == documento.hash_sha256
    assert registro["remitente"] is None and registro["asunto_correo"] is None
    original = almacen / documento.ruta_original
    assert original.read_bytes() == simulado("01_informe_valido.xlsx").read_bytes()
    assert ultima_bitacora(conexion)[0] == "Recepción de documento"


def test_rechaza_un_reenvio_con_otro_nombre(conexion, almacen):
    """12 es copia exacta de 01 (RN02, CU02 4a): no se registra aunque llegue por otro canal."""
    primero = recibir(conexion, almacen, "01_informe_valido.xlsx")
    antes = contar_archivos(conexion)

    reenvio = recibir(conexion, almacen, "12_informe_valido_reenvio.xlsx", canal=SFTP)

    assert not reenvio.aceptado
    assert reenvio.motivo is MotivoRechazo.DUPLICADO
    assert reenvio.id_archivo_existente == primero.documento.id_archivo
    assert contar_archivos(conexion) == antes
    accion, detalle = ultima_bitacora(conexion)
    assert accion == "Recepción rechazada" and detalle["id_archivo_existente"] == primero.documento.id_archivo


@pytest.mark.parametrize("nombre, tipo, estado", [
    # Todo informe de deudores pasa por la extracción, también los estructurados (sin OCR).
    ("02_informe_valido.csv", "CSV", "Pendiente de Extracción"),
    ("03_informe_latin1.txt", "TXT", "Pendiente de Extracción"),
    ("10_informe_corrupto.xlsx", "Excel", "Pendiente de Extracción"),  # el archivo dañado lo detecta la extracción (RN04)
    ("13_informe_valido.docx", "Word", "Pendiente de Extracción"),
    ("21_informe_pdf_texto.pdf", "PDF con texto", "Pendiente de Extracción"),
    ("23_informe_escaneado.pdf", "PDF escaneado", "Pendiente de Extracción"),
    ("24_foto_informe.jpg", "Imagen", "Pendiente de Extracción"),
])
def test_clasifica_el_tipo_de_documento(conexion, almacen, nombre, tipo, estado):
    documento = recibir(conexion, almacen, nombre).documento
    assert (documento.tipo_documento, documento.estado_archivo) == (tipo, estado)


def test_un_pdf_danado_queda_como_escaneado_para_la_extraccion(conexion, almacen):
    resultado = recibir_documento(conexion, b"%PDF-1.4 esto no es un pdf", "nomina.pdf", WEB,
                                  almacen=almacen, tamano_maximo=MB)
    assert resultado.documento.tipo_documento == "PDF escaneado"


@pytest.mark.parametrize("nombre, contenido, tamano_maximo, motivo", [
    ("informe.odt", b"contenido", MB, MotivoRechazo.TIPO_NO_PERMITIDO),
    ("programa.exe", b"MZ", MB, MotivoRechazo.TIPO_NO_PERMITIDO),
    ("sin_extension", b"contenido", MB, MotivoRechazo.TIPO_NO_PERMITIDO),
    ("vacia.csv", b"", MB, MotivoRechazo.VACIO),
    ("grande.csv", b"x" * 11, 10, MotivoRechazo.DEMASIADO_GRANDE),
])
def test_rechaza_sin_registrar_ni_guardar(conexion, almacen, nombre, contenido, tamano_maximo, motivo):
    antes = contar_archivos(conexion)

    resultado = recibir_documento(conexion, contenido, nombre, WEB, almacen=almacen, tamano_maximo=tamano_maximo)

    assert resultado.motivo is motivo
    assert contar_archivos(conexion) == antes
    assert not almacen.exists() or not any(almacen.rglob("*.*"))
    assert ultima_bitacora(conexion)[0] == "Recepción rechazada"


def test_guarda_los_datos_del_correo(conexion, almacen):
    from datetime import datetime
    correo = DatosCorreo("nominas@tgr.cl", "Nómina octubre", datetime(2026, 10, 1, 9, 30))

    documento = recibir(conexion, almacen, "02_informe_valido.csv", canal=CORREO, correo=correo).documento

    registro = fila(conexion, documento.id_archivo)
    assert (registro["remitente"], registro["asunto_correo"]) == ("nominas@tgr.cl", "Nómina octubre")
    assert registro["fecha_correo"] == datetime(2026, 10, 1, 9, 30)


def test_los_datos_del_correo_son_solo_del_canal_correo(conexion, almacen):
    with pytest.raises(ValueError):
        recibir(conexion, almacen, "02_informe_valido.csv", canal=WEB, correo=DatosCorreo("a@b.cl", None, None))
    with pytest.raises(ValueError):
        recibir(conexion, almacen, "02_informe_valido.csv", canal=CORREO)
