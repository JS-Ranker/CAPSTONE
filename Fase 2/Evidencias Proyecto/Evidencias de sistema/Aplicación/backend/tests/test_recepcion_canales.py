"""Pruebas de los canales de recepción (correo y SFTP), la extracción de pendientes y la API de carga web."""
import os
import shutil
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.modulos.recepcion import (
    WEB, procesar_pendientes, recibir_documento, revisar_buzon, revisar_directorio, ruta_plantilla,
)
from app.modulos.recepcion import api
from app.modulos.recepcion import correo as modulo_correo
from app.modulos.recepcion.correo import CorreoRecibido
from tests.conftest import simulado
from tests.test_recepcion import MB, fila, recibir, ultima_bitacora

AUTORIZADOS = ("nominas@tgr.cl",)


# --- Extracción de los documentos pendientes (CU02 paso 5 -> CU12) ----------------------------------------

def test_normaliza_un_pdf_con_texto_pendiente(conexion, almacen):
    documento = recibir(conexion, almacen, "21_nomina_pdf_texto.pdf").documento

    resumen = procesar_pendientes(conexion, almacen)

    assert (resumen.normalizados, resumen.con_error) == (1, 0)
    registro = fila(conexion, documento.id_archivo)
    assert (registro["estado_archivo"], registro["total_registros"]) == ("Normalizado", 25)
    assert float(registro["confianza_extraccion"]) == 100.0
    assert ruta_plantilla(almacen / documento.ruta_original).is_file()
    accion, detalle = ultima_bitacora(conexion)
    assert accion == "Extracción de documento" and detalle["estado"] == "Normalizado"


def test_un_pdf_cuyos_totales_no_cuadran_queda_con_error_de_extraccion(conexion, almacen):
    documento = recibir(conexion, almacen, "22_nomina_pdf_texto_totales_no_cuadran.pdf").documento

    procesar_pendientes(conexion, almacen)

    assert fila(conexion, documento.id_archivo)["estado_archivo"] == "Error de Extracción"
    assert not ruta_plantilla(almacen / documento.ruta_original).exists()


def test_un_pdf_ilegible_no_detiene_el_lote(conexion, almacen):
    danado = recibir_documento(conexion, b"%PDF-1.4 roto", "roto.pdf", WEB, almacen=almacen, tamano_maximo=MB)
    bueno = recibir(conexion, almacen, "21_nomina_pdf_texto.pdf")

    resumen = procesar_pendientes(conexion, almacen)

    assert (resumen.normalizados, resumen.con_error) == (1, 1)
    assert fila(conexion, danado.documento.id_archivo)["estado_archivo"] == "Error de Extracción"
    assert fila(conexion, bueno.documento.id_archivo)["estado_archivo"] == "Normalizado"
    assert procesar_pendientes(conexion, almacen).procesados == 0  # volver a ejecutar no repite nada


# --- Canal SFTP (CU02 1b) ----------------------------------------------------------------------------------

def test_revisa_el_directorio_sftp(conexion, almacen, tmp_path):
    entrada = tmp_path / "sftp"
    entrada.mkdir()
    for nombre in ("01_nomina_valida.xlsx", "12_nomina_valida_reenvio.xlsx", "02_nomina_valida.csv"):
        shutil.copy(simulado(nombre), entrada / nombre)
    (entrada / "virus.exe").write_bytes(b"MZ")
    (entrada / "subiendo.csv.part").write_bytes(b"incompleto")
    (entrada / "recien_llegado.txt").write_bytes(simulado("03_nomina_latin1.txt").read_bytes())
    hace_dos_minutos = os.path.getmtime(entrada / "virus.exe") - 120
    for ruta in entrada.iterdir():
        if ruta.name != "recien_llegado.txt":
            os.utime(ruta, (hace_dos_minutos, hace_dos_minutos))

    resumen = revisar_directorio(conexion, entrada, almacen=almacen, tamano_maximo=20 * MB, antiguedad_minima=60)

    assert (resumen.registrados, resumen.rechazados, resumen.fallidos) == (2, 2, 0)  # 12 es duplicado de 01; .exe
    assert resumen.omitidos == 2  # el .part y el que aún se está copiando
    restantes = sorted(ruta.name for ruta in entrada.iterdir() if ruta.is_file())
    assert restantes == ["recien_llegado.txt", "subiendo.csv.part"]
    assert len(list((entrada / "procesados").rglob("*.*"))) == 2
    rechazados = sorted(ruta.name for ruta in (entrada / "rechazados").rglob("*.*"))
    assert rechazados == ["12_nomina_valida_reenvio.xlsx", "virus.exe"]
    canales = conexion.execute(text("SELECT DISTINCT canal_origen FROM dbo.Archivos_TGR")).scalars().all()
    assert canales == ["SFTP"]


def test_sftp_no_sobrescribe_un_procesado_con_el_mismo_nombre(conexion, almacen, tmp_path):
    entrada = tmp_path / "sftp"
    entrada.mkdir()
    for nombre in ("02_nomina_valida.csv", "05_nomina_lote2_con_duplicados.csv"):
        ruta = entrada / "nomina.csv"
        ruta.write_bytes(simulado(nombre).read_bytes())
        # En Windows la fecha de un archivo recién escrito puede quedar unos milisegundos por delante de
        # time.time(): se fecha en el pasado para que cuente como copiado.
        hace_dos_minutos = ruta.stat().st_mtime - 120
        os.utime(ruta, (hace_dos_minutos, hace_dos_minutos))
        revisar_directorio(conexion, entrada, almacen=almacen, tamano_maximo=20 * MB, antiguedad_minima=60)

    assert sorted(r.name for r in (entrada / "procesados").rglob("*.*")) == ["nomina.csv", "nomina_1.csv"]


# --- Canal de correo (CU02 pasos 1, 2 y 7) -----------------------------------------------------------------

class BuzonEnMemoria:
    def __init__(self, correos: dict[str, EmailMessage]):
        self.correos = correos
        self.procesados: list[str] = []

    def no_leidos(self):
        return [CorreoRecibido(uid, mensaje.as_bytes()) for uid, mensaje in self.correos.items()
                if uid not in self.procesados]

    def marcar_procesado(self, uid):
        self.procesados.append(uid)


def correo(remitente, asunto, *adjuntos) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["From"] = f"Tesorería <{remitente}>"
    mensaje["To"] = "conciliacion@banco-generico.cl"
    mensaje["Subject"] = asunto
    mensaje["Date"] = "Thu, 01 Oct 2026 09:30:00 -0300"
    mensaje.set_content("Se adjunta la nómina.")
    for nombre in adjuntos:
        mensaje.add_attachment(simulado(nombre).read_bytes(), maintype="application",
                               subtype="octet-stream", filename=nombre)
    return mensaje


def test_revisa_la_casilla_de_correo(conexion, almacen):
    buzon = BuzonEnMemoria({
        "1": correo("Nominas@TGR.cl", "Nóminas octubre", "02_nomina_valida.csv", "21_nomina_pdf_texto.pdf"),
        "2": correo("phishing@ejemplo.com", "Urgente", "01_nomina_valida.xlsx"),
        "3": correo("nominas@tgr.cl", "Sin adjunto"),
    })

    resumen = revisar_buzon(conexion, buzon, remitentes_autorizados=AUTORIZADOS, almacen=almacen,
                            tamano_maximo=20 * MB)

    assert (resumen.registrados, resumen.rechazados, resumen.fallidos, resumen.omitidos) == (2, 0, 0, 2)
    assert buzon.procesados == ["1", "2", "3"]  # todos quedan leídos, también el ignorado
    registros = conexion.execute(text(
        "SELECT nombre_archivo, remitente, asunto_correo, fecha_correo FROM dbo.Archivos_TGR ORDER BY nombre_archivo"
    )).all()
    assert [r.nombre_archivo for r in registros] == ["02_nomina_valida.csv", "21_nomina_pdf_texto.pdf"]
    assert {(r.remitente, r.asunto_correo) for r in registros} == {("nominas@tgr.cl", "Nóminas octubre")}
    esperado = datetime.fromisoformat("2026-10-01T09:30:00-03:00").astimezone().replace(tzinfo=None)
    assert registros[0].fecha_correo == esperado
    acciones = conexion.execute(text("SELECT accion_ejecutada FROM dbo.Bitacora_Trazabilidad")).scalars().all()
    assert "Correo ignorado: remitente no autorizado" in acciones and "Correo sin adjuntos" in acciones

    # Revisar de nuevo no repite nada: los correos ya quedaron leídos
    repetida = revisar_buzon(conexion, buzon, remitentes_autorizados=AUTORIZADOS, almacen=almacen,
                             tamano_maximo=20 * MB)
    assert repetida.registrados == 0


def test_registra_la_foto_insertada_en_el_cuerpo_como_lo_hace_gmail(conexion, almacen):
    """Gmail deja dentro del cuerpo (multipart/related, inline) la foto arrastrada al texto; antes se perdía."""
    mensaje = EmailMessage()
    mensaje["From"] = "nominas@tgr.cl"
    mensaje["Subject"] = "Nómina fotografiada"
    mensaje.set_content("Adjunto la foto de la nómina.")
    mensaje.add_alternative('<p>Adjunto la foto.<img src="cid:foto"></p><p><img src="cid:logo"></p>', subtype="html")
    html = mensaje.get_payload()[1]
    html.add_related(simulado("24_foto_nomina.jpg").read_bytes(), maintype="image", subtype="jpeg",
                     cid="<foto>", filename="24_foto_nomina.jpg", disposition="inline")
    html.add_related(b"\x89PNG logo de la firma", maintype="image", subtype="png",
                     cid="<logo>", filename="logo_tgr.png", disposition="inline")  # pequeña: se ignora
    mensaje.add_attachment(simulado("08_nomina_sin_pie.csv").read_bytes(), maintype="text", subtype="csv",
                           filename="08_nomina_sin_pie.csv")

    resumen = revisar_buzon(conexion, BuzonEnMemoria({"1": mensaje}), remitentes_autorizados=AUTORIZADOS,
                            almacen=almacen, tamano_maximo=20 * MB)

    assert (resumen.registrados, resumen.rechazados) == (2, 0)
    registrados = conexion.execute(text(
        "SELECT nombre_archivo, tipo_documento FROM dbo.Archivos_TGR ORDER BY nombre_archivo")).all()
    assert [tuple(fila) for fila in registrados] == [("08_nomina_sin_pie.csv", "CSV"), ("24_foto_nomina.jpg", "Imagen")]


def test_si_falla_un_correo_queda_sin_leer_para_reintentar(conexion, almacen, monkeypatch):
    buzon = BuzonEnMemoria({"1": correo("nominas@tgr.cl", "Nómina", "02_nomina_valida.csv")})

    def falla(*args, **kwargs):
        raise ConnectionError("sin base de datos")
    monkeypatch.setattr(modulo_correo, "recibir_documento", falla)

    resumen = revisar_buzon(conexion, buzon, remitentes_autorizados=AUTORIZADOS, almacen=almacen,
                            tamano_maximo=20 * MB)

    assert resumen.fallidos == 1 and buzon.procesados == []


def test_sin_remitentes_autorizados_no_se_revisa(conexion, almacen):
    with pytest.raises(ValueError):
        revisar_buzon(conexion, BuzonEnMemoria({}), remitentes_autorizados=(), almacen=almacen, tamano_maximo=MB)


# --- API de carga web (CU02 1a) ----------------------------------------------------------------------------

@pytest.fixture
def cliente(conexion, almacen, tmp_path):
    extracciones: list[int] = []
    procesamientos: list[bool] = []
    buzon = BuzonEnMemoria({})
    sftp = tmp_path / "sftp"
    sftp.mkdir()
    app.dependency_overrides[api.obtener_conexion] = lambda: conexion
    app.dependency_overrides[api.obtener_almacen] = lambda: almacen
    app.dependency_overrides[api.obtener_extractor] = lambda: extracciones.append
    app.dependency_overrides[api.obtener_procesador_pendientes] = lambda: (lambda: procesamientos.append(True))
    app.dependency_overrides[api.obtener_buzon] = lambda: (lambda: nullcontext(buzon))
    app.dependency_overrides[api.obtener_directorio_sftp] = lambda: sftp
    try:
        with TestClient(app) as cliente:
            cliente.extracciones, cliente.procesamientos = extracciones, procesamientos
            cliente.buzon, cliente.sftp = buzon, sftp
            yield cliente
    finally:
        app.dependency_overrides.clear()


def cargar(cliente, nombre_simulado):
    ruta = simulado(nombre_simulado)
    return cliente.post("/api/recepcion/archivos", files={"archivo": (ruta.name, ruta.read_bytes())})


def test_api_carga_y_consulta_un_documento(cliente):
    respuesta = cargar(cliente, "01_nomina_valida.xlsx")
    assert respuesta.status_code == 201, respuesta.json()
    creado = respuesta.json()
    assert (creado["tipo_documento"], creado["estado_archivo"]) == ("Excel", "Recibido")
    assert cliente.extracciones == []  # los Excel no pasan por la extracción

    detalle = cliente.get(f"/api/recepcion/archivos/{creado['id_archivo']}").json()
    assert (detalle["nombre_archivo"], detalle["canal_origen"]) == ("01_nomina_valida.xlsx", "Web")
    assert "ruta_original" not in detalle and "hash_sha256" not in detalle

    lista = cliente.get("/api/recepcion/archivos", params={"limite": 5}).json()
    assert lista["archivos"][0]["id_archivo"] == creado["id_archivo"] and lista["limite"] == 5


def test_api_programa_la_extraccion_de_un_pdf(cliente):
    respuesta = cargar(cliente, "21_nomina_pdf_texto.pdf")
    assert respuesta.status_code == 201
    assert respuesta.json()["estado_archivo"] == "Pendiente de Extracción"
    assert cliente.extracciones == [respuesta.json()["id_archivo"]]


def test_api_rechaza_un_reenvio_con_409(cliente):
    primero = cargar(cliente, "01_nomina_valida.xlsx").json()
    respuesta = cargar(cliente, "12_nomina_valida_reenvio.xlsx")
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["motivo"] == "DUPLICADO"
    assert respuesta.json()["detail"]["id_archivo_existente"] == primero["id_archivo"]


def test_api_rechaza_tipos_no_permitidos_vacios_y_grandes(cliente, monkeypatch):
    no_permitido = cliente.post("/api/recepcion/archivos", files={"archivo": ("nomina.docx", b"x")})
    assert no_permitido.status_code == 415 and no_permitido.json()["detail"]["motivo"] == "TIPO_NO_PERMITIDO"
    assert cliente.post("/api/recepcion/archivos", files={"archivo": ("nomina.csv", b"")}).status_code == 400
    monkeypatch.setattr(api, "settings", replace(api.settings, tamano_maximo_mb=0))
    assert cliente.post("/api/recepcion/archivos", files={"archivo": ("nomina.csv", b"x")}).status_code == 413


def test_api_leer_correo_ahora(cliente):
    assert cliente.post("/api/recepcion/remitentes", json={"correo": "nominas@tgr.cl"}).status_code == 201
    cliente.buzon.correos["1"] = correo("nominas@tgr.cl", "Nómina", "02_nomina_valida.csv", "21_nomina_pdf_texto.pdf")

    respuesta = cliente.post("/api/recepcion/revisar/correo")

    assert respuesta.status_code == 200, respuesta.json()
    assert respuesta.json()["registrados"] == 2
    assert cliente.procesamientos == [True]  # el PDF se normaliza en segundo plano
    estado = cliente.get("/api/recepcion/estado").json()
    assert estado["correo"]["recibidos_hoy"] == 2 and estado["correo"]["ultima_revision"] is not None
    assert estado["pendientes_extraccion"] == 1


def test_api_forzar_lectura_sftp(cliente):
    archivo = cliente.sftp / "02_nomina_valida.csv"
    shutil.copy(simulado("02_nomina_valida.csv"), archivo)
    hace_un_minuto = archivo.stat().st_mtime - 60
    os.utime(archivo, (hace_un_minuto, hace_un_minuto))

    respuesta = cliente.post("/api/recepcion/revisar/sftp")

    assert respuesta.status_code == 200 and respuesta.json()["registrados"] == 1
    estado = cliente.get("/api/recepcion/estado").json()
    assert estado["sftp"]["configurado"] and estado["sftp"]["recibidos_hoy"] == 1


def test_api_leer_correo_sin_configuracion_responde_409(cliente, monkeypatch):
    app.dependency_overrides.pop(api.obtener_buzon)  # se usa la fábrica real, que revisa la configuración
    monkeypatch.setattr(api, "settings", replace(api.settings, imap_servidor=""))

    respuesta = cliente.post("/api/recepcion/revisar/correo")

    assert respuesta.status_code == 409
    assert cliente.get("/api/recepcion/estado").json()["correo"]["configurado"] is False


def test_api_leer_correo_sin_remitentes_responde_409(cliente):
    respuesta = cliente.post("/api/recepcion/revisar/correo")

    assert respuesta.status_code == 409 and "remitentes" in respuesta.json()["detail"].lower()
    assert cliente.get("/api/recepcion/estado").json()["correo"]["remitentes_autorizados"] == 0


def test_api_administra_los_remitentes_autorizados(cliente, conexion):
    creado = cliente.post("/api/recepcion/remitentes", json={"correo": " TGR <Nominas@TGR.cl> ", "nombre": "TGR"})
    assert creado.status_code == 201, creado.json()
    assert (creado.json()["correo"], creado.json()["nombre"]) == ("nominas@tgr.cl", "TGR")
    assert ultima_bitacora(conexion)[0] == "Remitente autorizado agregado"

    repetido = cliente.post("/api/recepcion/remitentes", json={"correo": "nominas@tgr.cl"})
    assert repetido.status_code == 200 and repetido.json()["id_remitente"] == creado.json()["id_remitente"]
    assert [r["correo"] for r in cliente.get("/api/recepcion/remitentes").json()] == ["nominas@tgr.cl"]

    id_remitente = creado.json()["id_remitente"]
    assert cliente.delete(f"/api/recepcion/remitentes/{id_remitente}").status_code == 204
    assert ultima_bitacora(conexion)[0] == "Remitente autorizado quitado"
    assert cliente.get("/api/recepcion/remitentes").json() == []
    assert cliente.delete(f"/api/recepcion/remitentes/{id_remitente}").status_code == 404

    reactivado = cliente.post("/api/recepcion/remitentes", json={"correo": "nominas@tgr.cl"})
    assert reactivado.status_code == 201 and reactivado.json()["id_remitente"] == id_remitente
    assert reactivado.json()["nombre"] == "TGR"  # conserva el nombre anterior


@pytest.mark.parametrize("correo", ["", "nominas", "nominas@tgr", "dos @tgr.cl", "a@b@tgr.cl"])
def test_api_rechaza_remitentes_con_formato_invalido(cliente, correo):
    respuesta = cliente.post("/api/recepcion/remitentes", json={"correo": correo})
    assert respuesta.status_code == 400
    assert cliente.get("/api/recepcion/remitentes").json() == []


def test_api_responde_404_y_valida_la_paginacion(cliente):
    assert cliente.get("/api/recepcion/archivos/999999999").status_code == 404
    assert cliente.get("/api/recepcion/archivos", params={"limite": 101}).status_code == 422
    assert cliente.get("/api/recepcion/archivos", params={"desplazamiento": -1}).status_code == 422
