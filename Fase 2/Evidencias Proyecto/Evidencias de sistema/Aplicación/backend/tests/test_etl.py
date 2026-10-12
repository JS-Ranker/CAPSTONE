"""Pruebas del ETL de casos TGR (RF02, RF03) contra las reglas de Normalizar_TGR.ktr.

La muestra data/muestra_tgr/resultado_tgr_20261012.csv trae en esperado.json el resultado de cada fila:
el ETL en Python debe dar exactamente lo mismo que el de Pentaho.
"""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.config import BACKEND_DIR
from app.modulos.etl.carga import CARGADO, DUPLICADO, RECHAZADO, ErrorFormatoCsv, ejecutar, leer_csv
from app.modulos.etl.reglas import (
    COLUMNAS_CSV, COLUMNAS_STG, Caso, Rechazo, digito_verificador, limpiar_rut, normalizar, separar_rol,
    separar_tesoreria,
)

MUESTRA = BACKEND_DIR.parent / "data" / "muestra_tgr"
CSV_MUESTRA = MUESTRA / "resultado_tgr_20261012.csv"
# Textos de esperado.json -> resultado en etl.resultados
RESULTADOS = {"Carga en": CARGADO, "Rechazado": RECHAZADO, "Descartado": DUPLICADO}


def fila_valida(**cambios):
    fila = {
        "nombre_documento": "20261012", "rut": "46822128", "dv": "4", "id_demanda": "689183", "n_resol": "79612",
        "nom_cli": " francisco muñoz díaz ", "monto_solicitado": "403000", "saldo_menor_05_utm": "0",
        "tipo_embargo": "retención", "rol": "30237-2022 SANTIAGO", "fec_ing": "12-10-2026",
        "tesoreria": "TESORERÍA REGIONAL DE SANTIAGO", "fecha_oficio": "10-10-2026", "mult_rol": "NO",
        "rev_manual": "NO", "camp_falt": "", "ent_banco": "BANCO GENÉRICO", "id_correo": "<1@tgr.cl>",
        "remit": "notificaciones@tgr.cl", "asunto": "Oficio", "ruta_doc": "documentos/oficio_0001.pdf",
    }
    return {**fila, **cambios}


def esperado():
    return json.loads((MUESTRA / "esperado.json").read_text(encoding="utf-8"))


# --- Reglas (sin base de datos) ---

@pytest.mark.parametrize("rut, dv", [
    ("46822128", "4"), ("12345678", "5"), ("11111111", "1"), ("15555555", "6"), ("15555567", "K"),
])
def test_digito_verificador(rut, dv):
    assert digito_verificador(rut) == dv


@pytest.mark.parametrize("rut, dv, esperado_rut, valido", [
    ("46822128", "4", "46822128", True),
    ("46.822.128", "4", "46822128", True),     # con puntos
    ("46822128-", " 4 ", "46822128", True),    # guion y espacios
    ("046822128", "4", "46822128", True),      # cero a la izquierda: el .ktr lee el RUT como número
    ("15555567", "k", "15555567", True),       # k minúscula
    ("46822128", "5", "46822128", False),      # DV que no calza
    ("123456", "0", "123456", False),          # menos de 7 dígitos
    ("", "", "", False),
])
def test_limpiar_rut(rut, dv, esperado_rut, valido):
    rut_limpio, _, es_valido = limpiar_rut(rut, dv)
    assert (rut_limpio, es_valido) == (esperado_rut, valido)


@pytest.mark.parametrize("rol, partes", [
    ("1532-2024 VALPARAÍSO", ("1532", 2024, "VALPARAÍSO")),
    ("  1532 - 2024   SAN BERNARDO ", ("1532", 2024, "SAN BERNARDO")),
    ("ROL SIN NÚMERO", None),
    ("1532-24 SANTIAGO", None),                # año de 2 dígitos
    ("1532-2024", None),                       # sin localidad
])
def test_separar_rol(rol, partes):
    assert separar_rol(rol) == partes


@pytest.mark.parametrize("tesoreria, partes", [
    ("TESORERÍA REGIONAL DE SANTIAGO", ("REGIONAL", "SANTIAGO")),
    ("TESORERIA PROVINCIAL DEL MAIPO", ("PROVINCIAL", "MAIPO")),
    ("TESORERÍA REGIONAL ANTOFAGASTA", ("REGIONAL", "ANTOFAGASTA")),
    ("OFICINA CENTRAL", None),
])
def test_separar_tesoreria(tesoreria, partes):
    assert separar_tesoreria(tesoreria) == partes


def test_normalizar_caso_valido():
    caso = normalizar(fila_valida(tesoreria=" tesorería provincial del maipo ", rol=" 1532 - 2024 san bernardo "))
    assert isinstance(caso, Caso)
    c = caso.columnas
    assert (c["rut_limpio"], c["dv_limpio"], c["nom_cli"]) == ("46822128", "4", "FRANCISCO MUÑOZ DÍAZ")
    assert (c["rol"], c["rol_cod"], c["rol_anio"], c["rol_loc"]) == ("1532 - 2024 SAN BERNARDO", "1532", 2024,
                                                                     "SAN BERNARDO")
    assert (c["tesoreria_tipo"], c["tesoreria_loc"]) == ("PROVINCIAL", "MAIPO")
    assert (c["fec_ing"], c["fecha_oficio"]) == (date(2026, 10, 12), date(2026, 10, 10))
    assert c["monto_solicitado"] == Decimal("403000")
    assert c["est_ret"] == "RETENCIÓN"                        # TIPO EMBARGO -> est_ret
    assert (c["mult_rol_bit"], c["rev_manual_bit"]) == (False, False)
    assert c["camp_falt"] is None                             # vacío -> nulo
    assert caso.llave == ("46822128", "4", "1532 - 2024 SAN BERNARDO", date(2026, 10, 12))


def test_normalizar_tesoreria_sin_formato_no_rechaza():
    caso = normalizar(fila_valida(tesoreria="OFICINA CENTRAL"))
    assert isinstance(caso, Caso)
    assert (caso.columnas["tesoreria_tipo"], caso.columnas["tesoreria_loc"]) == (None, None)


@pytest.mark.parametrize("cambios, motivo", [
    ({"mult_rol": "QUIZÁS"}, "MULTIPLES ROLES debe ser SI o NO"),
    ({"rev_manual": ""}, "REVISION MANUAL debe ser SI o NO"),
    ({"dv": "5"}, "RUT o DV inválido"),
    ({"rol": "ROL SIN NÚMERO"}, "EXPEDIENTE sin formato"),
    ({"fec_ing": ""}, "Falta FECHA INGRESO CASILLA"),
    ({"fec_ing": "2026-10-12"}, "FECHA INGRESO CASILLA no es dd-mm-aaaa"),
    ({"fecha_oficio": "31-02-2026"}, "FECHA OFICIO no es dd-mm-aaaa"),
    ({"monto_solicitado": "403.000"}, "MONTO SOLICITADO no es un número entero"),
    ({"nom_cli": "X" * 251}, "nom_cli supera los 250 caracteres"),
])
def test_normalizar_rechazos(cambios, motivo):
    resultado = normalizar(fila_valida(**cambios))
    assert isinstance(resultado, Rechazo)
    assert resultado.motivo.startswith(motivo)


def test_indicadores_se_validan_antes_que_la_llave():
    """Mismo orden que el .ktr: con indicador y RUT malos, el motivo es el indicador."""
    resultado = normalizar(fila_valida(mult_rol="TAL VEZ", dv="5"))
    assert resultado.motivo.startswith("MULTIPLES ROLES")


def test_si_con_tilde_es_valido():
    caso = normalizar(fila_valida(mult_rol="sí", rev_manual="Si"))
    assert (caso.columnas["mult_rol_bit"], caso.columnas["rev_manual_bit"]) == (True, True)


# --- Lectura del CSV ---

def test_leer_csv_de_muestra():
    filas = leer_csv(CSV_MUESTRA)
    assert len(filas) == 35
    assert list(filas[0]) == list(COLUMNAS_STG)
    assert filas[0]["nombre_documento"] == "20261012"         # sin el BOM pegado al primer valor


@pytest.mark.parametrize("contenido, mensaje", [
    ("", "vacío"),
    ("A;B;C\n1;2;3\n", "Se esperaban 21 columnas"),
    (";".join(COLUMNAS_CSV) + "\n" + ";".join(["x"] * 20) + "\n", "La fila 2 tiene 20 columnas"),
])
def test_leer_csv_con_formato_incorrecto(tmp_path, contenido, mensaje):
    ruta = tmp_path / "malo.csv"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(ErrorFormatoCsv, match=mensaje):
        leer_csv(ruta)


def test_leer_csv_que_no_es_utf8(tmp_path):
    ruta = tmp_path / "latin1.csv"
    ruta.write_bytes((";".join(COLUMNAS_CSV) + "\n").encode("latin-1"))  # "N° Resolución" en Latin-1
    with pytest.raises(ErrorFormatoCsv, match="UTF-8"):
        leer_csv(ruta)


# --- Ejecución completa contra SQL Server ---

def contar(conexion, tabla):
    return conexion.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar_one()


def test_ejecutar_muestra_da_el_resultado_esperado(conexion_etl):
    resumen = ejecutar(conexion_etl, CSV_MUESTRA)

    assert (resumen.filas_leidas, resumen.cargadas, resumen.rechazadas, resumen.duplicadas) == (35, 28, 5, 2)
    assert contar(conexion_etl, "core.casos_tgr") == 28
    assert contar(conexion_etl, "stg.casos_tgr") == 35
    obtenidos = conexion_etl.execute(text(
        "SELECT r.resultado FROM etl.resultados r WHERE r.id_ejecucion = :id ORDER BY r.id_stg"
    ), {"id": resumen.id_ejecucion}).scalars().all()
    esperados = [next(v for k, v in RESULTADOS.items() if fila["resultado"].startswith(k))
                 for fila in esperado()["filas"]]
    assert obtenidos == esperados                              # fila por fila, en el orden del CSV

    ejecucion = conexion_etl.execute(text("SELECT * FROM etl.ejecuciones WHERE id_ejecucion = :id"),
                                     {"id": resumen.id_ejecucion}).mappings().one()
    assert (ejecucion["cargadas"], ejecucion["rechazadas"], ejecucion["duplicadas"]) == (28, 5, 2)
    accion, detalle = conexion_etl.execute(text(
        "SELECT TOP 1 accion_ejecutada, detalle_cambio FROM dbo.Bitacora_Trazabilidad ORDER BY id_bitacora DESC"
    )).one()
    assert accion == "Ejecución ETL"
    assert json.loads(detalle)["cargadas"] == 28


def test_rechazados_quedan_con_motivo_y_duplicados_apuntan_al_caso(conexion_etl):
    resumen = ejecutar(conexion_etl, CSV_MUESTRA)
    filas = conexion_etl.execute(text(
        "SELECT resultado, motivo, id_caso FROM etl.resultados WHERE id_ejecucion = :id"
    ), {"id": resumen.id_ejecucion}).mappings().all()
    for fila in filas:
        if fila["resultado"] == RECHAZADO:
            assert fila["motivo"] and fila["id_caso"] is None
        else:
            assert fila["id_caso"] is not None
    duplicados = [f for f in filas if f["resultado"] == DUPLICADO]
    cargados = {f["id_caso"] for f in filas if f["resultado"] == CARGADO}
    assert all(d["id_caso"] in cargados for d in duplicados)


def test_cargar_dos_veces_el_mismo_archivo_no_duplica_casos(conexion_etl):
    ejecutar(conexion_etl, CSV_MUESTRA)
    segunda = ejecutar(conexion_etl, CSV_MUESTRA)

    assert (segunda.cargadas, segunda.rechazadas, segunda.duplicadas) == (0, 5, 30)
    assert contar(conexion_etl, "core.casos_tgr") == 28


def test_csv_invalido_no_deja_nada_a_medias(conexion_etl, tmp_path):
    filas = CSV_MUESTRA.read_text(encoding="utf-8-sig").splitlines()
    columnas = filas[2].split(";")
    columnas[0] = "X" * 300                                    # NOMBRE DOCUMENTO: stg admite 255
    ruta = tmp_path / "largo.csv"
    ruta.write_text("\n".join([filas[0], filas[1], ";".join(columnas)]) + "\n", encoding="utf-8")

    with pytest.raises(ErrorFormatoCsv, match="La fila 3"):
        ejecutar(conexion_etl, ruta)
    for tabla in ("etl.ejecuciones", "stg.casos_tgr", "core.casos_tgr"):
        assert contar(conexion_etl, tabla) == 0


# --- API ---

@pytest.fixture
def cliente(conexion_etl, almacen):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.modulos.recepcion import api as recepcion_api

    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion_etl
    app.dependency_overrides[recepcion_api.obtener_almacen] = lambda: almacen
    app.dependency_overrides[recepcion_api.obtener_extractor] = lambda: (lambda id_archivo: None)
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()


def subir(cliente, nombre, contenido):
    return cliente.post("/api/recepcion/archivos", files={"archivo": (nombre, contenido)})


def test_api_subir_csv_tgr_lo_procesa(cliente, conexion_etl):
    respuesta = subir(cliente, CSV_MUESTRA.name, CSV_MUESTRA.read_bytes())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado_archivo"] == "Procesado"
    assert (cuerpo["etl"]["cargadas"], cuerpo["etl"]["rechazadas"], cuerpo["etl"]["duplicadas"]) == (28, 5, 2)
    archivo = cliente.get(f"/api/recepcion/archivos/{cuerpo['id_archivo']}").json()
    assert (archivo["estado_archivo"], archivo["total_registros"]) == ("Procesado", 35)
    ejecucion = cliente.get(f"/api/etl/archivos/{cuerpo['id_archivo']}").json()
    assert ejecucion["cargadas"] == 28

    repetido = cliente.post(f"/api/etl/archivos/{cuerpo['id_archivo']}")
    assert repetido.status_code == 409


def test_api_csv_con_otro_formato_no_pasa_por_el_etl(cliente):
    from tests.conftest import simulado

    ruta = simulado("02_informe_valido.csv")
    respuesta = subir(cliente, ruta.name, ruta.read_bytes())
    assert respuesta.status_code == 201
    # Es un informe de deudores (no el CSV resultado_tgr): va a la extracción, no directo al ETL.
    assert (respuesta.json()["estado_archivo"], respuesta.json()["etl"]) == ("Pendiente de Extracción", None)

    forzado = cliente.post(f"/api/etl/archivos/{respuesta.json()['id_archivo']}")
    assert forzado.status_code == 409                          # no es para este ETL: el documento no cambia
    archivo = cliente.get(f"/api/recepcion/archivos/{respuesta.json()['id_archivo']}").json()
    assert archivo["estado_archivo"] == "Pendiente de Extracción"


def test_api_procesar_csv_tgr_recibido_por_otro_canal(cliente, conexion_etl, almacen):
    """Correo y SFTP no corren el ETL al recibir: se procesa después con POST /api/etl/archivos/{id}."""
    from app.modulos.recepcion.registro import SFTP, recibir_documento

    recibido = recibir_documento(conexion_etl, CSV_MUESTRA.read_bytes(), CSV_MUESTRA.name, SFTP,
                                 almacen=almacen, tamano_maximo=1024 * 1024)
    respuesta = cliente.post(f"/api/etl/archivos/{recibido.documento.id_archivo}")
    assert respuesta.status_code == 201
    assert respuesta.json()["cargadas"] == 28


def test_api_csv_tgr_con_fila_mala_queda_en_error(cliente, conexion_etl):
    encabezado = CSV_MUESTRA.read_text(encoding="utf-8-sig").splitlines()[0]
    contenido = (encabezado + "\n" + ";".join(["x"] * 5) + "\n").encode("utf-8")
    respuesta = subir(cliente, "resultado_tgr_malo.csv", contenido)

    assert respuesta.status_code == 201
    assert respuesta.json()["estado_archivo"] == "Error"
    assert "La fila 2 tiene 5 columnas" in respuesta.json()["etl"]["error"]
    assert contar(conexion_etl, "core.casos_tgr") == 0


def test_api_procesar_archivo_inexistente(cliente):
    assert cliente.post("/api/etl/archivos/999999999").status_code == 404
    assert cliente.get("/api/etl/archivos/999999999").status_code == 404


def test_api_casos_busqueda_y_revision(cliente):
    subir(cliente, CSV_MUESTRA.name, CSV_MUESTRA.read_bytes())

    todos = cliente.get("/api/casos", params={"limite": 100}).json()
    assert (todos["total"], len(todos["casos"])) == (28, 28)
    assert todos["en_revision"] == 1                           # la fila con OCR incompleto
    primero = todos["casos"][0]
    assert {"rut_limpio", "dv_limpio", "nom_cli", "rol", "monto_solicitado", "rev_manual_bit"} <= set(primero)

    rut = esperado()["filas"][0]["rut"]                        # "46822128-4"
    por_rut = cliente.get("/api/casos", params={"buscar": rut}).json()
    assert por_rut["total"] == 1 and por_rut["casos"][0]["rut_limpio"] == rut.split("-")[0]
    con_puntos = f"{int(rut.split('-')[0]):,}".replace(",", ".")
    assert cliente.get("/api/casos", params={"buscar": con_puntos}).json()["total"] == 1
    assert cliente.get("/api/casos", params={"revision": True}).json()["total"] == 1
    assert cliente.get("/api/casos", params={"buscar": "%"}).json()["total"] == 0  # comodín escapado

    pagina = cliente.get("/api/casos", params={"limite": 10, "desplazamiento": 20}).json()
    assert len(pagina["casos"]) == 8


def test_api_rechazados_con_motivo(cliente):
    subir(cliente, CSV_MUESTRA.name, CSV_MUESTRA.read_bytes())

    rechazados = cliente.get("/api/etl/rechazados").json()
    assert rechazados["total"] == 5
    motivos = sorted(r["motivo"].split(" ")[0] for r in rechazados["rechazados"])
    assert motivos == ["EXPEDIENTE", "Falta", "MULTIPLES", "REVISION", "RUT"]
    assert all(r["rut"] is not None for r in rechazados["rechazados"])
    # nombre original del documento, sin la huella que se le antepone en el almacén
    assert {r["archivo_origen"] for r in rechazados["rechazados"]} == {CSV_MUESTRA.name}


# --- Trazabilidad del lote (historial y documento original) ---

def test_api_historial_del_lote(cliente, conexion_etl):
    from app import bitacora

    id_archivo = subir(cliente, CSV_MUESTRA.name, CSV_MUESTRA.read_bytes()).json()["id_archivo"]
    # Un registro de otro lote cuyo id empieza igual (p. ej. 17 y 178) no debe aparecer.
    bitacora.registrar(conexion_etl, "Recepción de documento", {"id_archivo": int(f"{id_archivo}8")})

    historial = cliente.get(f"/api/recepcion/archivos/{id_archivo}/historial").json()
    assert [h["accion"] for h in historial] == ["Recepción de documento", "Ejecución ETL"]
    assert historial[0]["detalle"]["canal"] == "Web"
    assert historial[1]["detalle"]["cargadas"] == 28
    assert all(h["usuario"] for h in historial)
    assert cliente.get("/api/recepcion/archivos/999999999/historial").status_code == 404


def test_api_documento_del_lote(cliente):
    id_archivo = subir(cliente, CSV_MUESTRA.name, CSV_MUESTRA.read_bytes()).json()["id_archivo"]

    respuesta = cliente.get(f"/api/recepcion/archivos/{id_archivo}/documento")
    assert respuesta.status_code == 200
    assert respuesta.content == CSV_MUESTRA.read_bytes()
    assert respuesta.headers["content-disposition"].startswith("attachment")  # un CSV se descarga, no se abre
    assert cliente.get("/api/recepcion/archivos/999999999/documento").status_code == 404


# --- Filtro por informe ---

def test_api_filtrar_por_informe(cliente):
    muestra = subir(cliente, CSV_MUESTRA.name, CSV_MUESTRA.read_bytes()).json()["id_archivo"]
    otro = subir(cliente, "otro_resultado_tgr.csv",
                 CSV_MUESTRA.read_bytes().replace(b"12-10-2026", b"13-10-2026")).json()["id_archivo"]

    casos = cliente.get("/api/casos", params={"informe": muestra, "limite": 100}).json()
    assert casos["total"] == 28 and {c["id_informe"] for c in casos["casos"]} == {muestra}
    assert cliente.get("/api/casos", params={"limite": 100}).json()["total"] > 28   # el otro informe también cargó

    rechazados = cliente.get("/api/etl/rechazados", params={"informe": otro}).json()
    assert rechazados["total"] == 5 and {r["id_archivo"] for r in rechazados["rechazados"]} == {otro}

    # En Ingesta, cada informe dice cuántos deudores esperan revisión (1 caso dudoso + 5 rechazados).
    informes = {a["id_archivo"]: a for a in cliente.get("/api/recepcion/archivos").json()["archivos"]}
    assert informes[muestra]["por_revisar"] == 6

    excepciones = cliente.get("/api/excepciones", params={"informe": muestra, "estado": "Pendiente"}).json()
    assert excepciones["total"] == 6 and excepciones["pendientes"] == {"caso": 1, "rechazo": 5}
    assert {e["id_informe"] for e in excepciones["excepciones"]} == {muestra}
