"""Pruebas de la Bandeja de Excepciones (CU05, RF05, RN05) con la muestra TGR cargada por el ETL.

La muestra deja 1 caso para revisión manual (OCR sin fecha de oficio ni n° de resolución) y 5 filas rechazadas.
"""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import BACKEND_DIR
from app.main import app
from app.modulos.etl.carga import ejecutar
from app.modulos.etl.reglas import digito_verificador
from app.modulos.excepciones import servicio
from app.modulos.excepciones.servicio import (
    CASO, DESCARTADO, PENDIENTE, RECHAZO, RESUELTO, AccionNoPermitida, DatosInvalidos, ExcepcionNoEncontrada,
)
from app.modulos.recepcion import api as recepcion_api

CSV_MUESTRA = BACKEND_DIR.parent / "data" / "muestra_tgr" / "resultado_tgr_20261012.csv"


@pytest.fixture
def bandeja(conexion_etl):
    ejecutar(conexion_etl, CSV_MUESTRA)
    return conexion_etl


def listar(conexion, **filtros):
    return servicio.listar(conexion, tipo=filtros.get("tipo"), estado=filtros.get("estado"),
                           buscar=filtros.get("buscar"), limite=100, desplazamiento=0)


def caso_en_revision(conexion):
    return listar(conexion, tipo=CASO)["excepciones"][0]


def rechazo(conexion, motivo):
    return next(e for e in listar(conexion, tipo=RECHAZO)["excepciones"] if e["motivo"].startswith(motivo))


def contar(conexion, tabla):
    return conexion.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar_one()


# --- Listado y detalle ---

def test_listar_muestra_casos_y_rechazos_pendientes(bandeja):
    todas = listar(bandeja)
    assert todas["total"] == 6
    assert todas["pendientes"] == {CASO: 1, RECHAZO: 5}
    assert {e["estado"] for e in todas["excepciones"]} == {PENDIENTE}
    caso = caso_en_revision(bandeja)
    assert caso["motivo"] == "Datos vacíos o poco legibles: FECHA OFICIO, N° RESOLUCIÓN"
    assert caso["archivo_origen"] == CSV_MUESTRA.name
    assert listar(bandeja, buscar=f"{caso['rut']}-{caso['dv']}")["total"] == 1


def test_detalle_trae_datos_regla_e_historial(bandeja):
    caso = caso_en_revision(bandeja)
    detalle = servicio.detalle(bandeja, CASO, caso["id"])
    assert detalle["datos"]["fecha_oficio"] is None and detalle["datos"]["n_resol"] is None
    assert detalle["historial"] == []

    fila = rechazo(bandeja, "RUT o DV")
    detalle = servicio.detalle(bandeja, RECHAZO, fila["id"])
    assert set(detalle["datos"]) >= {"rut", "dv", "rol", "fec_ing", "mult_rol"}   # tal como llegó (stg)


def test_detalle_inexistente(bandeja):
    with pytest.raises(ExcepcionNoEncontrada):
        servicio.detalle(bandeja, CASO, 999999999)


# --- Caso marcado para revisión ---

def test_regularizar_caso_completa_datos_y_deja_historial(bandeja):
    caso = caso_en_revision(bandeja)
    resultado = servicio.revisar_caso(bandeja, caso["id"], "regularizar", " Revisado contra el oficio original ",
                                      {"fecha_oficio": "05-10-2026", "n_resol": "55123"})
    assert resultado.estado == RESUELTO

    fila = bandeja.execute(text("SELECT fecha_oficio, n_resol, rev_manual_bit FROM core.casos_tgr WHERE id_caso = :id"),
                           {"id": caso["id"]}).one()
    assert (fila.fecha_oficio, fila.n_resol, fila.rev_manual_bit) == (date(2026, 10, 5), "55123", False)
    historial = servicio.detalle(bandeja, CASO, caso["id"])["historial"]
    assert len(historial) == 1
    assert historial[0]["observacion"] == "Revisado contra el oficio original"
    assert historial[0]["cambios"] == {"fecha_oficio": {"antes": None, "despues": "2026-10-05"},
                                       "n_resol": {"antes": None, "despues": "55123"}}
    assert listar(bandeja)["pendientes"][CASO] == 0
    assert listar(bandeja, estado=RESUELTO)["total"] == 1                       # sigue visible, ya resuelto
    accion, detalle = bandeja.execute(text(
        "SELECT TOP 1 accion_ejecutada, detalle_cambio FROM dbo.Bitacora_Trazabilidad ORDER BY id_bitacora DESC"
    )).one()
    assert accion == "Revisión de excepción"
    assert json.loads(detalle)["campos_corregidos"] == ["fecha_oficio", "n_resol"]

    with pytest.raises(AccionNoPermitida):
        servicio.revisar_caso(bandeja, caso["id"], "regularizar", "Otra vez")


def test_dejar_pendiente_guarda_lo_corregido_sin_resolver(bandeja):
    caso = caso_en_revision(bandeja)
    resultado = servicio.revisar_caso(bandeja, caso["id"], "pendiente", "Falta pedir el oficio a la TGR",
                                      {"n_resol": "55123"})
    assert resultado.estado == PENDIENTE
    fila = bandeja.execute(text("SELECT n_resol, rev_manual_bit FROM core.casos_tgr WHERE id_caso = :id"),
                           {"id": caso["id"]}).one()
    assert (fila.n_resol, fila.rev_manual_bit) == ("55123", True)
    assert caso_en_revision(bandeja)["observacion"] == "Falta pedir el oficio a la TGR"


@pytest.mark.parametrize("accion, observacion, cambios, campo", [
    ("regularizar", "  ", {}, "observacion"),
    ("regularizar", "ok", {"fecha_oficio": "2026-10-05"}, "fecha_oficio"),
    ("regularizar", "ok", {"monto_solicitado": "1.000"}, "monto_solicitado"),
    ("regularizar", "ok", {"rut_limpio": "1"}, "rut_limpio"),        # la llave del caso no se edita
    ("cargar", "ok", {}, "accion"),                                  # acción de filas rechazadas
])
def test_revisar_caso_con_datos_invalidos_no_cambia_nada(bandeja, accion, observacion, cambios, campo):
    caso = caso_en_revision(bandeja)
    with pytest.raises(DatosInvalidos) as error:
        servicio.revisar_caso(bandeja, caso["id"], accion, observacion, cambios)
    assert error.value.campo == campo
    assert contar(bandeja, "etl.revisiones") == 0


# --- Fila rechazada por el ETL ---

def test_corregir_y_cargar_rechazo_crea_el_caso(bandeja):
    fila = rechazo(bandeja, "RUT o DV")
    dv_correcto = digito_verificador(fila["rut"])
    casos_antes = contar(bandeja, "core.casos_tgr")

    resultado = servicio.revisar_rechazo(bandeja, fila["id"], "cargar", "DV mal digitado en el oficio",
                                         {"dv": dv_correcto})
    assert resultado.estado == RESUELTO and resultado.id_caso_nuevo is not None
    assert contar(bandeja, "core.casos_tgr") == casos_antes + 1
    nuevo = bandeja.execute(text("SELECT rut_limpio, dv_limpio FROM core.casos_tgr WHERE id_caso = :id"),
                            {"id": resultado.id_caso_nuevo}).one()
    assert tuple(nuevo) == (fila["rut"], dv_correcto)
    original = servicio.detalle(bandeja, RECHAZO, fila["id"])["datos"]
    assert original["dv"] == fila["dv"]                                          # stg queda como llegó
    with pytest.raises(AccionNoPermitida):
        servicio.revisar_rechazo(bandeja, fila["id"], "descartar", "ya no")


def test_cargar_rechazo_que_sigue_sin_cumplir_las_reglas(bandeja):
    fila = rechazo(bandeja, "EXPEDIENTE")
    with pytest.raises(DatosInvalidos, match="Todavía no cumple las reglas del ETL: EXPEDIENTE"):
        servicio.revisar_rechazo(bandeja, fila["id"], "cargar", "intento", {"rol": "SIN FORMATO"})
    assert contar(bandeja, "etl.revisiones") == 0


def test_cargar_rechazo_que_duplica_un_caso_existente(bandeja):
    existente = bandeja.execute(text("SELECT TOP 1 rut_limpio, dv_limpio, rol, fec_ing FROM core.casos_tgr")).one()
    fila = rechazo(bandeja, "Falta FECHA INGRESO")
    datos = {"rut": existente.rut_limpio, "dv": existente.dv_limpio, "rol": existente.rol,
             "fec_ing": existente.fec_ing.strftime("%d-%m-%Y")}
    with pytest.raises(AccionNoPermitida, match="Ya existe el caso"):
        servicio.revisar_rechazo(bandeja, fila["id"], "cargar", "intento", datos)


def test_descartar_y_reabrir_un_rechazo(bandeja):
    fila = rechazo(bandeja, "MULTIPLES ROLES")
    assert servicio.revisar_rechazo(bandeja, fila["id"], "descartar", "Oficio anulado por la TGR").estado == DESCARTADO
    with pytest.raises(AccionNoPermitida, match="reábrala"):
        servicio.revisar_rechazo(bandeja, fila["id"], "cargar", "intento", {"mult_rol": "NO"})

    assert servicio.revisar_rechazo(bandeja, fila["id"], "pendiente", "Se descartó por error").estado == PENDIENTE
    cargado = servicio.revisar_rechazo(bandeja, fila["id"], "cargar", "Indicador corregido", {"mult_rol": "NO"})
    assert cargado.estado == RESUELTO
    estados = [h["estado"] for h in servicio.detalle(bandeja, RECHAZO, fila["id"])["historial"]]
    assert estados == [RESUELTO, PENDIENTE, DESCARTADO]                        # el más reciente primero


# --- API ---

@pytest.fixture
def cliente(bandeja):
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: bandeja
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()


def test_api_bandeja(cliente, bandeja):
    lista = cliente.get("/api/excepciones", params={"estado": "Pendiente"}).json()
    assert lista["total"] == 6
    caso = next(e for e in lista["excepciones"] if e["tipo"] == CASO)
    assert cliente.get(f"/api/excepciones/caso/{caso['id']}").json()["datos"]["camp_falt"]
    assert cliente.get("/api/excepciones/caso/999999999").status_code == 404
    assert cliente.get("/api/excepciones", params={"tipo": "otro"}).status_code == 422

    invalida = cliente.post(f"/api/excepciones/caso/{caso['id']}/revisiones",
                            json={"accion": "regularizar", "observacion": "ok", "datos": {"fecha_oficio": "ayer"}})
    assert invalida.status_code == 422 and invalida.json()["detail"]["campo"] == "fecha_oficio"

    ok = cliente.post(f"/api/excepciones/caso/{caso['id']}/revisiones",
                      json={"accion": "regularizar", "observacion": "Revisado", "datos": {"n_resol": "1"}})
    assert ok.status_code == 201 and ok.json()["estado"] == RESUELTO
    repetida = cliente.post(f"/api/excepciones/caso/{caso['id']}/revisiones",
                            json={"accion": "regularizar", "observacion": "Revisado"})
    assert repetida.status_code == 409


# --- Documento original ("Ver documento") ---

def recibir_pdf(conexion, almacen, simulado_pdf, nombre, correo=None):
    from app.modulos.recepcion.registro import CORREO, WEB, recibir_documento
    from tests.conftest import simulado

    resultado = recibir_documento(conexion, simulado(simulado_pdf).read_bytes(), nombre, CORREO if correo else WEB,
                                  almacen=almacen, tamano_maximo=20 * 1024 * 1024, correo=correo)
    return resultado.documento.id_archivo


def nombre_pdf_del_caso(conexion):
    from app.modulos.recepcion.documentos import nombre_en_ruta

    ruta = servicio.detalle(conexion, CASO, caso_en_revision(conexion)["id"])["datos"]["ruta_doc"]
    return nombre_en_ruta(ruta)                                               # "oficio_0909.pdf"


@pytest.mark.parametrize("ruta, nombre", [
    ("documentos/20261012/oficio_0909.pdf", "oficio_0909.pdf"),
    (r"C:\Users\tomas\TGR\pdf\oficio_0909.pdf", "oficio_0909.pdf"),          # ruta de Windows del equipo de origen
    ("  ", None),
    (None, None),
])
def test_nombre_en_ruta(ruta, nombre):
    from app.modulos.recepcion.documentos import nombre_en_ruta

    assert nombre_en_ruta(ruta) == nombre


def test_detalle_encuentra_el_pdf_recibido_con_el_mismo_nombre(bandeja, almacen):
    nombre = nombre_pdf_del_caso(bandeja)
    id_archivo = recibir_pdf(bandeja, almacen, "21_informe_pdf_texto.pdf", nombre)

    documento = servicio.detalle(bandeja, CASO, caso_en_revision(bandeja)["id"])["documento"]
    assert documento == {"nombre_buscado": nombre, "id_archivo": id_archivo}


def test_prefiere_el_pdf_del_mismo_remitente(bandeja, almacen):
    from app.modulos.recepcion.registro import DatosCorreo

    nombre = nombre_pdf_del_caso(bandeja)
    datos = servicio.detalle(bandeja, CASO, caso_en_revision(bandeja)["id"])["datos"]
    del_correo = recibir_pdf(bandeja, almacen, "21_informe_pdf_texto.pdf", nombre,
                             DatosCorreo(remitente=datos["remit"], asunto=datos["asunto"], fecha=None))
    recibir_pdf(bandeja, almacen, "23_informe_escaneado.pdf", nombre)          # mismo nombre, más reciente, otro canal

    assert servicio.documento_original(bandeja, CASO, caso_en_revision(bandeja)["id"]).id_archivo == del_correo


def test_sin_pdf_recibido(bandeja):
    fila = rechazo(bandeja, "RUT o DV")
    detalle = servicio.detalle(bandeja, RECHAZO, fila["id"])
    assert detalle["documento"]["id_archivo"] is None
    with pytest.raises(ExcepcionNoEncontrada, match=detalle["documento"]["nombre_buscado"]):
        servicio.documento_original(bandeja, RECHAZO, fila["id"])


def test_ruta_segura_no_sale_del_almacen(tmp_path):
    from app.modulos.recepcion.documentos import DocumentoOriginal, ruta_segura

    (tmp_path / "secreto.txt").write_text("x")
    almacen = tmp_path / "almacen"
    almacen.mkdir()
    assert ruta_segura(almacen, DocumentoOriginal(1, "secreto.txt", "../secreto.txt")) is None
    assert ruta_segura(almacen, DocumentoOriginal(1, "no.pdf", "2026/10/no.pdf")) is None  # registrado, sin archivo


def test_api_ver_documento(bandeja, almacen):
    from tests.conftest import simulado

    nombre = nombre_pdf_del_caso(bandeja)
    recibir_pdf(bandeja, almacen, "21_informe_pdf_texto.pdf", nombre)
    caso = caso_en_revision(bandeja)
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: bandeja
    app.dependency_overrides[recepcion_api.obtener_almacen] = lambda: almacen
    try:
        with TestClient(app) as cliente:
            respuesta = cliente.get(f"/api/excepciones/caso/{caso['id']}/documento")
            assert respuesta.status_code == 200
            assert respuesta.headers["content-type"] == "application/pdf"
            assert respuesta.headers["content-disposition"].startswith("inline")
            assert respuesta.content == simulado("21_informe_pdf_texto.pdf").read_bytes()

            fila = rechazo(bandeja, "RUT o DV")
            sin_pdf = cliente.get(f"/api/excepciones/rechazo/{fila['id']}/documento")
            assert sin_pdf.status_code == 404 and "No se encontró" in sin_pdf.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_api_rechazados_muestra_el_estado_de_la_revision(cliente, bandeja):
    fila = rechazo(bandeja, "RUT o DV")
    antes = cliente.get("/api/etl/rechazados", params={"limite": 100}).json()
    assert antes["pendientes"] == antes["total"] == 5
    assert {r["estado_revision"] for r in antes["rechazados"]} == {PENDIENTE}

    resultado = servicio.revisar_rechazo(bandeja, fila["id"], "cargar", "DV corregido",
                                         {"dv": digito_verificador(fila["rut"])})

    despues = cliente.get("/api/etl/rechazados", params={"limite": 100}).json()
    assert (despues["total"], despues["pendientes"]) == (5, 4)
    corregida = next(r for r in despues["rechazados"] if r["id_resultado"] == fila["id"])
    assert (corregida["estado_revision"], corregida["id_caso_nuevo"]) == (RESUELTO, resultado.id_caso_nuevo)
