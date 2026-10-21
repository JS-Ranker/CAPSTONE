"""Pruebas del módulo de IA analítica (RF08, CU08): detección de anomalías, tendencias, reglas y servicio."""
import json
import random
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.modulos.etl.carga import ejecutar
from app.modulos.ia import servicio
from app.modulos.ia.deteccion import ALTO, BAJO, MEDIO, detectar, redondear_arriba
from app.modulos.ia.reglas import MONTO_MAXIMO, Regla, motivo_por_reglas
from app.modulos.ia.tendencias import CALIDAD, TENDENCIA, motivo_base, tendencias
from app.modulos.recepcion import api as recepcion_api
from app.modulos.recepcion import procesar_pendientes
from tests.conftest import SIMULADOS
from tests.test_recepcion import recibir

TESORERIAS = ["TESORERÍA REGIONAL DE SANTIAGO", "TESORERÍA REGIONAL DE VALPARAÍSO",
              "TESORERÍA REGIONAL DEL BIOBÍO"]
HOY = date(2026, 10, 12)


def generador(semilla=1):
    azar = random.Random(semilla)

    def caso(id_caso, informe, **cambios):
        base = {"id_caso": id_caso, "rut": str(azar.randint(40_000_000, 49_999_999)),
                "monto": azar.randint(20, 3000) * 1000.0, "tesoreria": azar.choice(TESORERIAS), "fec_ing": HOY,
                "fecha_oficio": HOY - timedelta(days=azar.randint(1, 30)), "rol_anio": azar.randint(2019, 2026),
                "id_informe": informe}
        return base | cambios
    return caso


# --- Detección (sin base de datos) ---

def test_encuentra_las_anomalias_sembradas_sin_falsas_alarmas():
    caso = generador()
    historial = [caso(i, 1 + i // 100) for i in range(300)]
    normales = [caso(1000 + i, 99) for i in range(30)]
    sembradas = [caso(2001, 99, monto=180_000_000.0), caso(2002, 99, fecha_oficio=date(2023, 5, 1)),
                 caso(2003, 99, fecha_oficio=date(2030, 1, 1)), caso(2004, 99, rol_anio=1995)]
    anomalias, info = detectar(historial, normales + sembradas)

    por_caso = {a.id_caso: a for a in anomalias}
    assert set(por_caso) == {2001, 2002, 2003, 2004}                 # ninguna falsa alarma entre los 30 normales
    assert (por_caso[2001].nivel, por_caso[2002].nivel, por_caso[2003].nivel, por_caso[2004].nivel) == \
        (ALTO, MEDIO, MEDIO, BAJO)
    assert anomalias[0].id_caso == 2001                              # ordenadas de más a menos grave
    assert "veces el monto habitual" in por_caso[2001].motivos[0].texto
    assert por_caso[2001].regla_sugerida == {"tipo": MONTO_MAXIMO, "valor": info["limite_monto"]}
    assert info["modelo"].startswith("IsolationForest")
    assert all(a.puntaje is not None for a in anomalias)


def test_un_rut_repetido_es_una_sola_alerta():
    caso = generador(2)
    historial = [caso(i, 1 + i // 100) for i in range(300)]
    repetidos = [caso(3000 + k, 99, rut="44444444") for k in range(5)]
    anomalias, _ = detectar(historial, [caso(1000 + i, 99) for i in range(20)] + repetidos)

    assert [a.id_caso for a in anomalias] == [3000]
    assert anomalias[0].nivel == ALTO                                 # 5 o más veces
    assert "#3000, #3001, #3002, #3003, #3004" in anomalias[0].motivos[0].texto


def test_con_poco_historial_usa_solo_reglas():
    caso = generador(3)
    anomalias, info = detectar([], [caso(i, 99) for i in range(20)] + [caso(99, 99, monto=900_000_000.0)])
    assert info["modelo"].startswith("Solo reglas")
    assert [a.id_caso for a in anomalias] == [99] and anomalias[0].puntaje is None


@pytest.mark.parametrize("valor, esperado", [(2_734_512, 2_800_000), (3_000_000, 3_000_000), (95_100, 96_000)])
def test_redondear_arriba(valor, esperado):
    assert redondear_arriba(valor) == esperado


# --- Tendencias de rechazo y calidad ---

def resumen(filas, rechazadas, en_revision=0, motivos=None, tipo="Excel"):
    return {"filas": filas, "rechazadas": rechazadas, "en_revision": en_revision,
            "motivos": Counter(motivos or {}), "tipo_documento": tipo}


def test_tendencia_de_rechazo_fuera_de_lo_habitual():
    actual = resumen(28, 7, motivos={"RUT o DV inválido": 3, "EXPEDIENTE sin formato": 1})
    hallazgos = tendencias(actual, [resumen(100, 2), resumen(120, 3)])
    assert [h.tipo for h in hallazgos] == [TENDENCIA]
    h = hallazgos[0]
    assert h.nivel == MEDIO and "25%" in h.titulo and "lo habitual es 2%" in h.detalle
    assert "«RUT o DV inválido» (3 de 7)" in h.detalle and "RUT" in h.sugerencia


def test_sin_alerta_si_los_rechazos_son_los_de_siempre():
    assert tendencias(resumen(100, 12), [resumen(100, 10), resumen(100, 14)]) == []


def test_calidad_del_documento_sugiere_pedir_otro_formato():
    hallazgos = tendencias(resumen(25, 0, en_revision=10, tipo="Imagen"), [])
    assert [(h.tipo, h.nivel) for h in hallazgos] == [(CALIDAD, MEDIO)]
    assert "Excel" in hallazgos[0].sugerencia


def test_informe_muy_chico_no_genera_tendencias():
    assert tendencias(resumen(3, 3), []) == []


def test_motivo_base():
    assert motivo_base("RUT o DV inválido (46030084-0)") == "RUT o DV inválido"


def test_regla_de_monto_maximo():
    reglas = [Regla(1, MONTO_MAXIMO, Decimal("3000000"))]
    assert motivo_por_reglas(Decimal("3500000"), reglas) == "MONTO SOBRE $3.000.000 (REGLA IA)"
    assert motivo_por_reglas(Decimal("2000000"), reglas) is None
    assert motivo_por_reglas(Decimal("9000000"), []) is None


# --- Servicio con SQL Server ---

@pytest.fixture
def con_historial(conexion_etl, almacen):
    """Tres informes válidos cargados (historial) y el informe con anomalías sembradas, ya analizado."""
    for nombre in ("01_informe_valido.xlsx", "02_informe_valido.csv", "03_informe_latin1.txt"):
        recibir(conexion_etl, almacen, nombre)
    procesar_pendientes(conexion_etl, almacen)
    informe = recibir(conexion_etl, almacen, "14_informe_con_anomalias.xlsx").documento.id_archivo
    procesar_pendientes(conexion_etl, almacen)
    return conexion_etl, informe


def manifiesto(nombre):
    datos = json.loads((SIMULADOS / "manifiesto.json").read_text(encoding="utf-8"))
    return next(a for a in datos["archivos"] if a["archivo"].endswith(nombre))


def test_el_analisis_corre_solo_despues_del_etl_y_encuentra_lo_sembrado(con_historial):
    conexion, informe = con_historial
    analisis = servicio.analisis_del_informe(conexion, informe)
    assert analisis and analisis["casos_analizados"] == 69 and analisis["casos_historial"] == 350
    assert analisis["modelo"].startswith("IsolationForest")

    insights = servicio.listar(conexion, informe=informe, nivel=None, estado=None, limite=100,
                               desplazamiento=0)["insights"]
    casos = {(r, e): i for i, r, e in conexion.execute(text(
        "SELECT id_caso, rut_limpio, rol FROM core.casos_tgr")).all()}
    alertas = {i["id_caso"]: i for i in insights if i["id_caso"]}
    sembradas = [r for r in manifiesto("14_informe_con_anomalias.xlsx")["registros"] if r.get("anomalia_esperada")]
    for registro in sembradas:
        id_caso = casos[(registro["rut"].split("-")[0], registro["expediente"].upper())]
        assert id_caso in alertas, registro["anomalia_esperada"]
        assert alertas[id_caso]["nivel"] == registro["anomalia_esperada"]["nivel"], registro["anomalia_esperada"]
    assert len(alertas) == len(sembradas)                            # sin falsas alarmas entre los 60 normales
    assert insights[0]["nivel"] == ALTO                              # ordenados de más a menos grave
    accion, = conexion.execute(text(
        "SELECT TOP 1 accion_ejecutada FROM dbo.Bitacora_Trazabilidad WHERE accion_ejecutada LIKE 'Análisis IA%' "
        "ORDER BY id_bitacora DESC")).one()
    assert accion == "Análisis IA"


def test_aplicar_la_sugerencia_cambia_el_siguiente_proceso(con_historial):
    conexion, informe = con_historial
    insights = servicio.listar(conexion, informe=informe, nivel=None, estado=None, limite=100,
                               desplazamiento=0)["insights"]
    con_regla = next(i for i in insights if i["aplicable"])
    assert servicio.revisar_insight(conexion, con_regla["id_insight"], "aplicar", "Montos altos a revisión") == \
        servicio.APLICADA
    valor = json.loads(con_regla["regla_sugerida"])["valor"]

    ejecutar(conexion, SIMULADOS.parent / "muestra_tgr" / "resultado_tgr_20261012.csv")
    marcados = conexion.execute(text(
        "SELECT monto_solicitado, rev_manual_bit, camp_falt FROM core.casos_tgr WHERE rut_limpio IN "
        "(SELECT rut FROM stg.casos_tgr WHERE archivo_origen = 'resultado_tgr_20261012.csv')")).all()
    assert any(m > valor for m, _, _ in marcados)
    for monto, revision, campos in marcados:
        assert ("REGLA IA" in (campos or "")) == (monto > valor)
        if monto > valor:
            assert revision

    with pytest.raises(servicio.AccionNoPermitida):
        servicio.revisar_insight(conexion, con_regla["id_insight"], "aplicar", None)


def test_marcar_como_revisado_y_resumen_del_dia(con_historial):
    conexion, informe = con_historial
    primero = servicio.listar(conexion, informe=informe, nivel=None, estado="Pendiente", limite=1,
                              desplazamiento=0)["insights"][0]
    assert servicio.revisar_insight(conexion, primero["id_insight"], "revisar", None) == servicio.REVISADA
    pendientes = servicio.listar(conexion, informe=informe, nivel=None, estado="Pendiente", limite=100,
                                 desplazamiento=0)
    assert primero["id_insight"] not in [i["id_insight"] for i in pendientes["insights"]]

    dia = servicio.resumen_dia(conexion, date.today())
    assert dia["informes"] == 4 and dia["deudores_leidos"] == 150 + 120 + 80 + 69
    assert sum(dia["alertas"].values()) >= 6 and any("La IA generó" in p for p in dia["puntos"])


def test_si_la_ia_falla_el_informe_igual_queda_procesado(conexion_etl, almacen, monkeypatch):
    def falla(*_):
        raise RuntimeError("modelo caído")
    monkeypatch.setattr(servicio, "detectar", falla)
    documento = recibir(conexion_etl, almacen, "02_informe_valido.csv").documento
    procesar_pendientes(conexion_etl, almacen)

    estado = conexion_etl.execute(text("SELECT estado_archivo FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                                  {"id": documento.id_archivo}).scalar_one()
    assert estado == "Procesado"
    accion = conexion_etl.execute(text(
        "SELECT TOP 1 accion_ejecutada FROM dbo.Bitacora_Trazabilidad ORDER BY id_bitacora DESC")).scalar_one()
    assert accion == "Análisis IA fallido"


def test_api_ia(con_historial):
    conexion, informe = con_historial
    app.dependency_overrides[recepcion_api.obtener_conexion] = lambda: conexion
    try:
        with TestClient(app) as cliente:
            lista = cliente.get("/api/ia/insights", params={"informe": informe}).json()
            assert lista["total"] >= 6 and lista["insights"][0]["nivel"] == ALTO
            assert lista["pendientes"][ALTO] >= 1
            assert cliente.get(f"/api/ia/informes/{informe}").json()["casos_analizados"] == 69
            assert cliente.get("/api/ia/informes/999999999").status_code == 404
            assert cliente.post("/api/ia/informes/999999999/analizar").status_code == 409
            assert cliente.post(f"/api/ia/informes/{informe}/analizar").status_code == 201
            primero = lista["insights"][0]["id_insight"]
            assert cliente.post(f"/api/ia/insights/{primero}/revision", json={"accion": "otra"}).status_code == 422
            resumen_hoy = cliente.get("/api/ia/resumen").json()
            assert resumen_hoy["informes"] == 4 and resumen_hoy["puntos"]
    finally:
        app.dependency_overrides.clear()


def test_niveles_son_los_de_la_tabla():
    assert {ALTO, MEDIO, BAJO} == set(servicio.NIVELES)
