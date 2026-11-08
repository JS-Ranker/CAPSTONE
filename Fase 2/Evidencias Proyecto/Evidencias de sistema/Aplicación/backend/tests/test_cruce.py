"""Pruebas del cruce con Banco Genérico (RF04) contra SQL Server: UTM, cruce de un informe, core simulado y API."""
import json
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.modulos.cruce import core_bancario, servicio, utm_oficial
from app.modulos.cruce.reglas import DESCONTADO, NO_DESCONTADO, PARCIAL, REVISION
from app.modulos.recepcion import api as recepcion_api
from app.modulos.recepcion import procesar_pendientes
from tests.test_recepcion import recibir, ultima_bitacora

UTM = Decimal("70000")  # 0,5 UTM = 35.000


@pytest.fixture
def informe(conexion_etl, almacen):
    """El informe 02 (120 deudores) recibido y procesado, sin UTM cargada: el cruce automático queda pendiente."""
    documento = recibir(conexion_etl, almacen, "02_informe_valido.csv").documento
    procesar_pendientes(conexion_etl, almacen)
    return documento.id_archivo


def periodo(conexion, id_archivo):
    recepcion = conexion.execute(text("SELECT fecha_recepcion FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                                 {"id": id_archivo}).scalar_one()
    return servicio.periodo_de(recepcion)


def casos(conexion, id_archivo):
    """(id_caso, rut, monto) de los casos del informe, del de menor id al de mayor."""
    return conexion.execute(text(
        "SELECT c.id_caso, c.rut_limpio, c.monto_solicitado FROM core.casos_tgr c "
        "JOIN etl.resultados r ON r.id_caso = c.id_caso AND r.resultado = N'Cargado' "
        "JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion WHERE e.id_archivo = :id ORDER BY c.id_caso"
    ), {"id": id_archivo}).all()


def agregar_cuenta(conexion, rut, numero, saldo, estado="Activa", tipo="Cuenta RUT"):
    conexion.execute(text("INSERT INTO banco.cuentas (rut, dv, numero_cuenta, tipo_cuenta, saldo, estado) "
                          "VALUES (:rut, '0', :numero, :tipo, :saldo, :estado)"),
                     {"rut": rut, "numero": numero, "tipo": tipo, "saldo": saldo, "estado": estado})


def resultado_de(cruce, id_caso):
    return next(r for r in cruce["resultados"] if r["id_caso"] == id_caso)


def test_sin_utm_el_cruce_automatico_queda_pendiente(conexion_etl, informe):
    assert servicio.cruce_del_informe(conexion_etl, informe) is None
    acciones = [a for (a,) in conexion_etl.execute(text(
        "SELECT accion_ejecutada FROM dbo.Bitacora_Trazabilidad ORDER BY id_bitacora DESC"))]
    assert acciones[0] == "Cruce pendiente"
    with pytest.raises(servicio.CruceNoPosible, match="UTM"):
        servicio.cruzar_informe(conexion_etl, informe)


def test_cruce_de_un_informe(conexion_etl, informe):
    todos = casos(conexion_etl, informe)
    grandes = [c for c in todos if c[2] > 200_000]   # deudas que 100.000 de saldo no alcanzan a cubrir
    (caso_c, rut_c, monto_c) = grandes[0]
    (caso_a, rut_a, monto_a), (caso_b, rut_b, _), (caso_d, rut_d, _) = [c for c in todos if c[0] != caso_c][:3]
    agregar_cuenta(conexion_etl, rut_a, "A1", monto_a + 100_000)                   # alcanza
    agregar_cuenta(conexion_etl, rut_b, "B1", 20_000)                              # bajo 0,5 UTM
    agregar_cuenta(conexion_etl, rut_c, "C1", 40_000, tipo="Cuenta de ahorro")     # alcanza en parte
    agregar_cuenta(conexion_etl, rut_c, "C2", 60_000)
    agregar_cuenta(conexion_etl, rut_d, "D1", 9_000_000, estado="Bloqueada")       # no cuenta
    servicio.fijar_utm(conexion_etl, periodo(conexion_etl, informe), UTM)

    resumen = servicio.cruzar_informe(conexion_etl, informe)
    assert resumen.casos == len(casos(conexion_etl, informe))
    assert resumen.clientes == 3
    assert resumen.valor_utm == UTM

    cruce = servicio.cruce_del_informe(conexion_etl, informe)
    a = resultado_de(cruce, caso_a)
    assert a["resultado"] == DESCONTADO and a["monto_descontado"] == monto_a and a["monto_pendiente"] == 0
    assert a["descuentos"] == [{"cuenta": "A1", "tipo": "Cuenta RUT", "monto": monto_a}]
    b = resultado_de(cruce, caso_b)
    assert b["resultado"] == NO_DESCONTADO and "0,5 UTM" in b["motivo"]
    c = resultado_de(cruce, caso_c)
    assert c["resultado"] == PARCIAL and c["monto_descontado"] == 100_000
    assert c["monto_pendiente"] == monto_c - 100_000
    assert [d["cuenta"] for d in c["descuentos"]] == ["C2", "C1"]   # primero la de mayor saldo
    d = resultado_de(cruce, caso_d)
    assert d["resultado"] == NO_DESCONTADO and d["cliente"] is False and "no es cliente" in d["motivo"].lower()

    saldo_menor = dict(conexion_etl.execute(text(
        "SELECT id_caso, saldo_menor_05_utm FROM core.casos_tgr WHERE id_caso IN (:a, :b, :d)"),
        {"a": caso_a, "b": caso_b, "d": caso_d}).all())
    assert saldo_menor == {caso_a: "NO", caso_b: "SI", caso_d: None}
    accion, detalle = ultima_bitacora(conexion_etl)
    assert accion == "Cruce con Banco Genérico" and detalle["id_archivo"] == informe


def test_volver_a_cruzar_crea_una_ejecucion_nueva_y_respeta_la_revision_manual(conexion_etl, informe):
    (caso_a, rut_a, monto_a), *_ = casos(conexion_etl, informe)
    agregar_cuenta(conexion_etl, rut_a, "A1", monto_a + 100_000)
    servicio.fijar_utm(conexion_etl, periodo(conexion_etl, informe), UTM)
    primera = servicio.cruzar_informe(conexion_etl, informe)

    conexion_etl.execute(text("UPDATE core.casos_tgr SET rev_manual_bit = 1 WHERE id_caso = :id"), {"id": caso_a})
    segunda = servicio.cruzar_informe(conexion_etl, informe)
    assert segunda.id_ejecucion > primera.id_ejecucion
    assert segunda.en_revision == primera.en_revision + 1
    cruce = servicio.cruce_del_informe(conexion_etl, informe)
    assert cruce["id_ejecucion"] == segunda.id_ejecucion
    assert resultado_de(cruce, caso_a)["resultado"] == REVISION


def test_fijar_utm_crea_o_corrige_el_mes(conexion_etl):
    servicio.fijar_utm(conexion_etl, "2026-10", Decimal("69000"))
    servicio.fijar_utm(conexion_etl, "2026-10", Decimal("69751.5"))
    assert servicio.valor_utm(conexion_etl, "2026-10") == Decimal("69751.50")
    accion, detalle = ultima_bitacora(conexion_etl)
    assert accion == "UTM actualizada" and detalle["anterior"] == "69000.00"


def test_obtener_la_utm_oficial_la_guarda_y_la_registra(conexion_etl, monkeypatch):
    monkeypatch.setattr(utm_oficial, "consultar", lambda periodo: Decimal("72151"))
    assert servicio.obtener_utm_oficial(conexion_etl, "2026-10") == Decimal("72151")
    assert servicio.valor_utm(conexion_etl, "2026-10") == Decimal("72151.00")
    accion, detalle = ultima_bitacora(conexion_etl)
    assert accion == "UTM oficial obtenida" and detalle["fuente"] == utm_oficial.FUENTE


def test_si_la_fuente_falla_no_se_toca_la_utm_ingresada(conexion_etl):
    servicio.fijar_utm(conexion_etl, "2026-10", Decimal("70000"))
    with pytest.raises(utm_oficial.UtmNoDisponible):
        servicio.obtener_utm_oficial(conexion_etl, "2026-10")
    assert servicio.valor_utm(conexion_etl, "2026-10") == Decimal("70000.00")


def test_el_cruce_automatico_busca_la_utm_oficial_si_falta(conexion_etl, informe, monkeypatch):
    monkeypatch.setattr(utm_oficial, "consultar", lambda periodo: Decimal("72151"))
    resumen = servicio.cruzar_sin_fallar(conexion_etl, informe)
    assert resumen is not None and resumen.valor_utm == Decimal("72151.00")


def test_la_consulta_de_la_utm_elige_el_mes_pedido(monkeypatch):
    import io
    import json as _json
    serie = {"serie": [{"fecha": "2026-11-01T03:00:00.000Z", "valor": 72440},
                       {"fecha": "2026-10-01T03:00:00.000Z", "valor": 72151},
                       {"fecha": "2026-09-01T04:00:00.000Z", "valor": 71721}]}
    monkeypatch.undo()   # deja la `consultar` real (la fixture autouse la había reemplazado)
    monkeypatch.setattr(utm_oficial, "urlopen", lambda *a, **k: io.StringIO(_json.dumps(serie)))
    assert utm_oficial.consultar("2026-10") == Decimal("72151")
    assert utm_oficial.consultar("2026-09") == Decimal("71721")
    with pytest.raises(utm_oficial.UtmNoDisponible, match="aún no publica"):
        utm_oficial.consultar("2026-12")


def test_api_utm_oficial(conexion_etl, monkeypatch):
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion_etl
    try:
        cliente = TestClient(app)
        assert cliente.post("/api/cruce/utm/2026-10/oficial").status_code == 502   # fuente caída
        monkeypatch.setattr(utm_oficial, "consultar", lambda periodo: Decimal("72151"))
        respuesta = cliente.post("/api/cruce/utm/2026-10/oficial")
        assert respuesta.status_code == 200 and respuesta.json()["valor"] == 72151
        assert cliente.get("/api/cruce/utm").json()[0]["periodo"] == "2026-10"
    finally:
        app.dependency_overrides.clear()


def test_carga_del_core_bancario(conexion_etl, tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_text("rut_titular;cuenta;codigo_banco;tipo_cuenta;saldo;estado_cuenta\n"
                    "40.000.001-K;111;099;Cuenta RUT;150000;Activa\n"
                    "40000002-5;222;099;Cuenta corriente;0;Cerrada\n", encoding="utf-8")
    cuentas = core_bancario.leer(ruta)
    assert cuentas[0]["rut"] == "40000001" and cuentas[0]["dv"] == "K"
    assert core_bancario.cargar(conexion_etl, cuentas, ruta.name) == core_bancario.ResumenCarga(2, 0)

    ruta.write_text(ruta.read_text(encoding="utf-8").replace("150000", "90000"), encoding="utf-8")
    assert core_bancario.cargar(conexion_etl, core_bancario.leer(ruta), ruta.name) == core_bancario.ResumenCarga(0, 2)
    assert conexion_etl.execute(text("SELECT saldo FROM banco.cuentas WHERE numero_cuenta = '111'")).scalar_one() \
        == 90_000


def test_el_core_bancario_rechaza_un_archivo_mal_formado(tmp_path):
    ruta = tmp_path / "cuentas.csv"
    ruta.write_text("rut_titular;cuenta;codigo_banco;estado_cuenta\n40000001-K;111;099;Activa\n", encoding="utf-8")
    with pytest.raises(core_bancario.ErrorCoreBancario, match="encabezado"):
        core_bancario.leer(ruta)
    ruta.write_text("rut_titular;cuenta;codigo_banco;tipo_cuenta;saldo;estado_cuenta\n"
                    "40000001-K;111;099;Cuenta RUT;-5;Activa\n", encoding="utf-8")
    with pytest.raises(core_bancario.ErrorCoreBancario, match="Fila 2"):
        core_bancario.leer(ruta)


def test_api_del_cruce(conexion_etl, informe):
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion_etl
    try:
        cliente = TestClient(app)
        assert cliente.get(f"/api/cruce/informes/{informe}").status_code == 404
        assert cliente.post(f"/api/cruce/informes/{informe}/cruzar").status_code == 409   # falta la UTM
        assert cliente.put("/api/cruce/utm/2026-13", json={"valor": 1}).status_code == 422
        assert cliente.put("/api/cruce/utm/2026-10", json={"valor": 0}).status_code == 422

        mes = periodo(conexion_etl, informe)
        assert cliente.put(f"/api/cruce/utm/{mes}", json={"valor": "70000"}).status_code == 200
        assert cliente.get("/api/cruce/utm").json()[0]["periodo"] == mes
        creado = cliente.post(f"/api/cruce/informes/{informe}/cruzar")
        assert creado.status_code == 201 and creado.json()["periodo"] == mes
        assert [c["id_archivo"] for c in cliente.get("/api/cruce/informes").json()] == [informe]
        cruce = cliente.get(f"/api/cruce/informes/{informe}").json()
        assert cruce["id_ejecucion"] == creado.json()["id_ejecucion"]
        assert {r["resultado"] for r in cruce["resultados"]} == {NO_DESCONTADO}   # nadie es cliente
        assert cliente.post("/api/cruce/informes/999999/cruzar").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_el_cruce_automatico_corre_despues_del_etl_si_hay_utm(conexion_etl, almacen):
    servicio.fijar_utm(conexion_etl, servicio.periodo_de(datetime.now()), UTM)
    documento = recibir(conexion_etl, almacen, "02_informe_valido.csv").documento
    procesar_pendientes(conexion_etl, almacen)
    cruce = servicio.cruce_del_informe(conexion_etl, documento.id_archivo)
    assert cruce is not None and cruce["casos"] == len(casos(conexion_etl, documento.id_archivo))
    detalle = json.loads(conexion_etl.execute(text(
        "SELECT TOP 1 detalle_cambio FROM dbo.Bitacora_Trazabilidad WHERE accion_ejecutada = N'Cruce con Banco Genérico' "
        "ORDER BY id_bitacora DESC")).scalar_one())
    assert detalle["id_archivo"] == documento.id_archivo
