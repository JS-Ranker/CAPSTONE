"""Pruebas de la revisión de informes con 'Error de Extracción' en la Bandeja de Excepciones (CU05, CU12 5b).

Se usa el PDF con texto cuyos montos no suman el total que declara (22_...): la extracción lo deja con error y
guarda lo que leyó; el analista corrige un monto y el informe pasa al ETL.
"""
import pytest
from sqlalchemy import text

from app.modulos.excepciones import documentos, servicio
from app.modulos.excepciones.documentos import FilaCorregida
from app.modulos.excepciones.servicio import (
    DESCARTADO, DOCUMENTO, PENDIENTE, RESUELTO, AccionNoPermitida, DatosInvalidos, ExcepcionNoEncontrada,
)
from app.modulos.recepcion import WEB, procesar_pendientes, recibir_documento
from tests.conftest import simulado

MB = 1024 * 1024


@pytest.fixture
def informe(conexion_etl, almacen):
    """Id de un informe con error de extracción por totales que no cuadran."""
    ruta = simulado("22_informe_pdf_texto_totales_no_cuadran.pdf")
    resultado = recibir_documento(conexion_etl, ruta.read_bytes(), ruta.name, WEB, almacen=almacen,
                                  tamano_maximo=20 * MB)
    procesar_pendientes(conexion_etl, almacen)
    return resultado.documento.id_archivo


def filas_de(detalle):
    return [FilaCorregida(f["orden"], dict(f["valores"])) for f in detalle["datos"]["extraccion"]["filas"]]


def corregida(detalle):
    """Filas y totales con el primer monto ajustado para que la suma coincida con el total declarado."""
    extraccion = detalle["datos"]["extraccion"]
    filas = filas_de(detalle)
    suma = sum(int(f.valores["monto_solicitado"]) for f in filas)
    primera = filas[0].valores
    primera["monto_solicitado"] = str(int(primera["monto_solicitado"]) + extraccion["suma_declarada"] - suma)
    return filas, extraccion["cantidad_declarada"], extraccion["suma_declarada"]


def estado_archivo(conexion, id_archivo):
    return conexion.execute(text("SELECT estado_archivo FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                            {"id": id_archivo}).scalar_one()


def test_el_informe_con_error_aparece_en_la_bandeja(conexion_etl, informe):
    lista = servicio.listar(conexion_etl, tipo=DOCUMENTO, estado=None, buscar=None, limite=20, desplazamiento=0)

    assert lista["pendientes"][DOCUMENTO] == 1
    fila = lista["excepciones"][0]
    assert (fila["tipo"], fila["id"], fila["estado"], fila["id_informe"]) == (DOCUMENTO, informe, PENDIENTE, informe)
    assert "monto total" in fila["motivo"]
    assert servicio.listar(conexion_etl, tipo=None, estado=None, buscar="totales_no_cuadran", limite=20,
                           desplazamiento=0)["total"] == 1


def test_detalle_trae_lo_extraido_con_su_confianza(conexion_etl, informe):
    detalle = documentos.detalle(conexion_etl, informe)

    extraccion = detalle["datos"]["extraccion"]
    assert extraccion["suma_declarada"] and extraccion["filas"]
    assert set(extraccion["filas"][0]["confianzas"]) == {c["campo"] for c in detalle["datos"]["columnas"]}
    assert detalle["documento"]["id_archivo"] == informe
    assert documentos.documento_original(conexion_etl, informe).id_archivo == informe


def test_informe_inexistente(conexion_etl):
    with pytest.raises(ExcepcionNoEncontrada):
        documentos.detalle(conexion_etl, 999999)


def test_corregir_y_procesar_carga_los_casos(conexion_etl, informe, almacen):
    detalle = documentos.detalle(conexion_etl, informe)
    filas, cantidad, suma = corregida(detalle)

    enviadas = documentos.procesar_corregido(conexion_etl, informe, "Corregí un monto leído de más",
                                             filas, cantidad, suma, almacen)

    assert enviadas == len(filas)
    assert estado_archivo(conexion_etl, informe) == "Procesado"
    assert conexion_etl.execute(text("SELECT COUNT(*) FROM etl.ejecuciones WHERE id_archivo = :id"),
                                {"id": informe}).scalar_one() == 1
    fila = servicio.listar(conexion_etl, tipo=DOCUMENTO, estado=None, buscar=None, limite=20,
                           desplazamiento=0)["excepciones"][0]
    assert fila["estado"] == RESUELTO
    historial = documentos.detalle(conexion_etl, informe)["historial"]
    assert historial[0]["estado"] == RESUELTO
    assert any("Monto solicitado" in clave for clave in historial[0]["cambios"])
    with pytest.raises(AccionNoPermitida):
        documentos.procesar_corregido(conexion_etl, informe, "otra vez", filas, cantidad, suma, almacen)


def test_si_los_totales_no_cuadran_no_se_carga_nada(conexion_etl, informe, almacen):
    detalle = documentos.detalle(conexion_etl, informe)
    extraccion = detalle["datos"]["extraccion"]

    with pytest.raises(DatosInvalidos, match="monto total"):
        documentos.procesar_corregido(conexion_etl, informe, "sin corregir", filas_de(detalle),
                                      extraccion["cantidad_declarada"], extraccion["suma_declarada"], almacen)

    assert estado_archivo(conexion_etl, informe) == "Error de Extracción"
    assert conexion_etl.execute(text("SELECT COUNT(*) FROM etl.ejecuciones")).scalar_one() == 0


def test_el_analista_puede_corregir_el_total_declarado(conexion_etl, informe, almacen):
    detalle = documentos.detalle(conexion_etl, informe)
    filas = filas_de(detalle)
    suma = sum(int(f.valores["monto_solicitado"]) for f in filas)

    documentos.procesar_corregido(conexion_etl, informe, "El total declarado estaba mal leído", filas,
                                  detalle["datos"]["extraccion"]["cantidad_declarada"], suma, almacen)

    cambios = documentos.detalle(conexion_etl, informe)["historial"][0]["cambios"]
    assert cambios["Monto total declarado"]["despues"] == suma


def test_montos_con_puntos_y_filas_agregadas_o_quitadas(conexion_etl, informe, almacen):
    detalle = documentos.detalle(conexion_etl, informe)
    filas = filas_de(detalle)
    ultima = filas.pop()  # se quita y se vuelve a digitar a mano, con puntos en el monto
    monto = int(ultima.valores["monto_solicitado"])
    filas.append(FilaCorregida(None, {**ultima.valores, "monto_solicitado": f"{monto:,}".replace(",", ".")}))
    suma = sum(int(f.valores["monto_solicitado"].replace(".", "")) for f in filas)

    documentos.procesar_corregido(conexion_etl, informe, "Volví a digitar la última fila", filas,
                                  detalle["datos"]["extraccion"]["cantidad_declarada"], suma, almacen)

    cambios = documentos.detalle(conexion_etl, informe)["historial"][0]["cambios"]
    assert cambios[f"Fila {ultima.orden}"]["despues"] == "quitada"
    assert "Fila nueva 1" in cambios
    assert conexion_etl.execute(text("SELECT COUNT(*) FROM core.casos_tgr WHERE monto_solicitado = :m"),
                                {"m": monto}).scalar_one() >= 1


def test_descartar_y_reabrir(conexion_etl, informe, almacen):
    assert documentos.revisar_documento(conexion_etl, informe, "descartar", "Foto ilegible") == DESCARTADO
    detalle = documentos.detalle(conexion_etl, informe)
    assert detalle["estado"] == DESCARTADO
    filas, cantidad, suma = corregida(detalle)
    with pytest.raises(AccionNoPermitida, match="descartado"):
        documentos.procesar_corregido(conexion_etl, informe, "intento", filas, cantidad, suma, almacen)

    assert documentos.revisar_documento(conexion_etl, informe, "pendiente", "Mejor lo reviso") == PENDIENTE


def test_la_observacion_es_obligatoria(conexion_etl, informe):
    with pytest.raises(DatosInvalidos):
        documentos.revisar_documento(conexion_etl, informe, "descartar", "  ")


def test_volver_a_extraer_deja_el_informe_pendiente_de_extraccion(conexion_etl, informe, almacen):
    documentos.volver_a_extraer(conexion_etl, informe, "Subieron una mejor versión")

    assert estado_archivo(conexion_etl, informe) == "Pendiente de Extracción"
    with pytest.raises(ExcepcionNoEncontrada):  # mientras se relee, el informe sale de la bandeja
        documentos.volver_a_extraer(conexion_etl, informe, "de nuevo")
    procesar_pendientes(conexion_etl, almacen)
    assert estado_archivo(conexion_etl, informe) == "Error de Extracción"  # el mismo PDF sigue sin cuadrar
    assert documentos.detalle(conexion_etl, informe)["datos"]["extraccion"]["filas"]
