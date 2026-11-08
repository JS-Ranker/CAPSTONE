"""Informe de respuesta a la TGR (RF07, RF11): a quiénes se descontó, a quiénes no y por qué.

Es un Excel con tres hojas:
- Resumen: el informe recibido, la UTM usada y los totales (recibidos, válidos, inválidos, clientes encontrados,
  descontados, no descontados y montos).
- Detalle: un renglón por caso cruzado, con deuda, saldo, descontado, pendiente, resultado y motivo.
- No procesados: las filas que el ETL rechazó y siguen sin resolver, con su motivo.

El sistema solo calcula: el cargo real lo hace el core bancario, así que el informe dice qué corresponde descontar.
"""
import io
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import Connection, text

from ...db import transaccion
from ..cruce.reglas import DESCONTADO, NO_DESCONTADO, PARCIAL, REVISION
from ..cruce.servicio import cruce_del_informe

COLOR_TITULO = "1F3864"
FORMATO_PESOS = '"$" #,##0'
FORMATO_FECHA = "dd-mm-yyyy"


class InformeNoEncontrado(Exception):
    pass


class SinCruce(Exception):
    """El informe aún no se ha cruzado con el banco: no hay nada que informar."""


def formatear_rut(rut: str, dv: str) -> str:
    cuerpo = f"{int(rut):,}".replace(",", ".") if str(rut).isdigit() else str(rut)
    return f"{cuerpo}-{dv}"


def recopilar(conexion: Connection, id_archivo: int) -> dict:
    """Datos del informe, de su cruce vigente y de lo que el ETL rechazó. Lanza SinCruce si no hay cruce."""
    with transaccion(conexion):
        archivo = conexion.execute(
            text("SELECT nombre_archivo, fecha_recepcion, remitente FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
            {"id": id_archivo}).mappings().one_or_none()
        if archivo is None:
            raise InformeNoEncontrado(f"No existe el informe {id_archivo}.")
        etl = conexion.execute(
            text("SELECT TOP 1 filas_leidas, cargadas, rechazadas, duplicadas FROM etl.ejecuciones "
                 "WHERE id_archivo = :id ORDER BY id_ejecucion DESC"), {"id": id_archivo}).mappings().one_or_none()
        rechazados = conexion.execute(
            text("SELECT s.rut, s.dv, s.nom_cli, s.id_demanda, s.n_resol, s.monto_solicitado, r.motivo "
                 "FROM etl.resultados r JOIN etl.ejecuciones e ON e.id_ejecucion = r.id_ejecucion "
                 "JOIN stg.casos_tgr s ON s.id_stg = r.id_stg "
                 "WHERE e.id_archivo = :id AND r.resultado = N'Rechazado' "
                 "AND ISNULL((SELECT TOP 1 v.estado FROM etl.revisiones v WHERE v.id_resultado = r.id_resultado "
                 "            ORDER BY v.id_revision DESC), N'Pendiente') = N'Pendiente' "
                 "ORDER BY r.id_resultado"), {"id": id_archivo}).mappings().all()
    cruce = cruce_del_informe(conexion, id_archivo)
    if cruce is None:
        raise SinCruce("El informe aún no se ha cruzado con Banco Genérico.")
    return {"archivo": dict(archivo), "etl": dict(etl) if etl else None, "cruce": cruce,
            "rechazados": [dict(f) for f in rechazados]}


def totales(datos: dict) -> dict[str, int | Decimal]:
    cruce, etl = datos["cruce"], datos["etl"]
    resultados = cruce["resultados"]
    validos = len(resultados)
    invalidos = len(datos["rechazados"])
    return {
        "recibidos": etl["filas_leidas"] if etl else validos + invalidos,
        "validos": validos,
        "invalidos": invalidos,
        "duplicados": etl["duplicadas"] if etl else 0,
        "clientes": sum(1 for r in resultados if r["cliente"]),
        "no_clientes": sum(1 for r in resultados if not r["cliente"]),
        "descontados": sum(1 for r in resultados if r["resultado"] == DESCONTADO),
        "parciales": sum(1 for r in resultados if r["resultado"] == PARCIAL),
        "no_descontados": sum(1 for r in resultados if r["resultado"] == NO_DESCONTADO),
        "en_revision": sum(1 for r in resultados if r["resultado"] == REVISION),
        "monto_solicitado": sum((r["monto_solicitado"] or Decimal(0) for r in resultados), Decimal(0)),
        "monto_descontado": sum((r["monto_descontado"] for r in resultados), Decimal(0)),
        "monto_pendiente": sum((r["monto_pendiente"] for r in resultados), Decimal(0)),
    }


def _encabezado(hoja, fila: int, titulos: list[str]) -> None:
    borde = Side(style="thin", color="BBBBBB")
    for columna, titulo in enumerate(titulos, start=1):
        celda = hoja.cell(fila, columna, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=COLOR_TITULO)
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celda.border = Border(left=borde, right=borde, top=borde, bottom=borde)
    hoja.row_dimensions[fila].height = 32


def _anchos(hoja, anchos: list[int]) -> None:
    for columna, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(columna)].width = ancho


def _fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    return valor if isinstance(valor, date) else None


def construir_excel(datos: dict) -> bytes:
    cruce, archivo, total = datos["cruce"], datos["archivo"], totales(datos)
    libro = Workbook()
    libro.properties.creator = "TTDH Automation"

    resumen = libro.active
    resumen.title = "Resumen"
    resumen["A1"] = "Respuesta a la Tesorería General de la República"
    resumen["A1"].font = Font(bold=True, size=14, color=COLOR_TITULO)
    resumen["A2"] = "Banco Genérico · resultado del cruce de los deudores informados"
    resumen["A2"].font = Font(italic=True, color="666666")
    datos_informe = [
        ("Informe recibido", archivo["nombre_archivo"]),
        ("Fecha de recepción", _fecha(archivo["fecha_recepcion"])),
        ("Remitente", archivo["remitente"] or "—"),
        ("Fecha del cruce", cruce["fecha"]),
        ("Periodo de la UTM", cruce["periodo"]),
        ("Valor de la UTM", cruce["valor_utm"]),
        ("Umbral de descuento (0,5 UTM)", cruce["valor_utm"] / 2),
    ]
    for fila, (rotulo, valor) in enumerate(datos_informe, start=4):
        resumen.cell(fila, 1, rotulo).font = Font(bold=True)
        celda = resumen.cell(fila, 2, valor)
        celda.alignment = Alignment(horizontal="left")
        if isinstance(valor, Decimal):
            celda.number_format = FORMATO_PESOS
        elif isinstance(valor, datetime):
            celda.number_format = "dd-mm-yyyy hh:mm"
        elif isinstance(valor, date):
            celda.number_format = FORMATO_FECHA
    inicio = 4 + len(datos_informe) + 1
    _encabezado(resumen, inicio, ["Indicador", "Valor"])
    indicadores = [
        ("Deudores recibidos", total["recibidos"], False),
        ("Válidos (cargados y cruzados)", total["validos"], False),
        ("Inválidos (rechazados al cargar)", total["invalidos"], False),
        ("Duplicados (ya informados antes)", total["duplicados"], False),
        ("Clientes de Banco Genérico encontrados", total["clientes"], False),
        ("No son clientes del banco", total["no_clientes"], False),
        ("Descontados por completo", total["descontados"], False),
        ("Descontados parcialmente", total["parciales"], False),
        ("No descontados", total["no_descontados"], False),
        ("En revisión", total["en_revision"], False),
        ("Monto solicitado por la TGR", total["monto_solicitado"], True),
        ("Monto a descontar", total["monto_descontado"], True),
        ("Monto pendiente", total["monto_pendiente"], True),
    ]
    for fila, (rotulo, valor, es_monto) in enumerate(indicadores, start=inicio + 1):
        resumen.cell(fila, 1, rotulo)
        celda = resumen.cell(fila, 2, valor)
        celda.number_format = FORMATO_PESOS if es_monto else "#,##0"
    nota = inicio + len(indicadores) + 2
    resumen.cell(nota, 1, "Regla: si el saldo total de las cuentas activas del cliente es menor a 0,5 UTM no se "
                          "descuenta; si no, se descuenta lo que alcance a cubrir la deuda. Varias deudas del mismo "
                          "RUT se cubren de la más antigua a la más nueva. El cargo real lo hace el core bancario.")
    resumen.cell(nota, 1).alignment = Alignment(wrap_text=True, vertical="top")
    resumen.merge_cells(start_row=nota, start_column=1, end_row=nota, end_column=2)
    resumen.row_dimensions[nota].height = 62
    _anchos(resumen, [44, 38])

    detalle = libro.create_sheet("Detalle")
    columnas = ["RUT", "Nombre", "Expediente", "ID demanda", "N° resolución", "Fecha oficio", "Deuda solicitada",
                "Saldo total en el banco", "Monto descontado", "Monto pendiente", "Resultado", "Motivo",
                "Cuentas descontadas"]
    _encabezado(detalle, 1, columnas)
    for fila, r in enumerate(cruce["resultados"], start=2):
        cuentas = "; ".join(f"{d['tipo']} N° {d['cuenta']}: ${int(d['monto']):,}".replace(",", ".")
                            for d in r["descuentos"])
        valores = [formatear_rut(r["rut"], r["dv"]), r["nombre"], r["rol"], r.get("id_demanda"), r.get("n_resol"),
                   _fecha(r["fecha_oficio"]), r["monto_solicitado"], r["saldo_total"], r["monto_descontado"],
                   r["monto_pendiente"], r["resultado"], r["motivo"], cuentas]
        for columna, valor in enumerate(valores, start=1):
            celda = detalle.cell(fila, columna, valor)
            if columna == 6:
                celda.number_format = FORMATO_FECHA
            elif 7 <= columna <= 10:
                celda.number_format = FORMATO_PESOS
            celda.alignment = Alignment(vertical="top", wrap_text=columna in (2, 12, 13))
    detalle.freeze_panes = "C2"
    detalle.auto_filter.ref = f"A1:{get_column_letter(len(columnas))}{max(len(cruce['resultados']) + 1, 2)}"
    _anchos(detalle, [14, 32, 24, 13, 14, 12, 16, 18, 16, 16, 18, 56, 52])

    no_procesados = libro.create_sheet("No procesados")
    columnas = ["RUT", "Nombre", "ID demanda", "N° resolución", "Monto solicitado", "Motivo del rechazo"]
    _encabezado(no_procesados, 1, columnas)
    for fila, r in enumerate(datos["rechazados"], start=2):
        rut = formatear_rut(r["rut"], r["dv"]) if r["rut"] and r["dv"] else (r["rut"] or "—")
        for columna, valor in enumerate([rut, r["nom_cli"], r["id_demanda"], r["n_resol"], r["monto_solicitado"],
                                         r["motivo"]], start=1):
            no_procesados.cell(fila, columna, valor).alignment = Alignment(vertical="top", wrap_text=columna in (2, 6))
    if not datos["rechazados"]:
        no_procesados.cell(2, 1, "Ningún deudor quedó sin procesar.")
    _anchos(no_procesados, [14, 32, 13, 14, 16, 70])

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def generar(conexion: Connection, id_archivo: int) -> tuple[bytes, str]:
    """El Excel del informe y el nombre con que se descarga."""
    datos = recopilar(conexion, id_archivo)
    base = datos["archivo"]["nombre_archivo"].rsplit(".", 1)[0]
    return construir_excel(datos), f"respuesta_tgr_{base}.xlsx"
