"""Avisos a los clientes con descuento (RF07): la lista de a quién avisar y el texto de cada aviso.

El sistema no envía correos: genera un Excel con un renglón por cliente (varias deudas del mismo RUT se juntan en
un solo aviso) para que el banco lo despache por sus canales.
"""
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment
from sqlalchemy import Connection

from .informe_tgr import FORMATO_PESOS, _anchos, _encabezado, formatear_rut, recopilar


def pesos(monto: Decimal | int) -> str:
    return f"${int(monto):,}".replace(",", ".")


def armar_avisos(cruce: dict) -> list[dict]:
    """Un aviso por RUT con monto a descontar, ordenado por RUT. Los no descontados no reciben aviso."""
    por_rut: dict[str, dict] = {}
    for r in cruce["resultados"]:
        if not r["cliente"] or r["monto_descontado"] <= 0:
            continue
        aviso = por_rut.setdefault(r["rut"], {
            "rut": formatear_rut(r["rut"], r["dv"]), "nombre": r["nombre"], "resoluciones": [], "expedientes": [],
            "descontado": Decimal(0), "pendiente": Decimal(0), "cuentas": {}})
        aviso["resoluciones"].append(str(r["n_resol"] or "s/n"))
        aviso["expedientes"].append(r["rol"])
        aviso["descontado"] += r["monto_descontado"]
        aviso["pendiente"] += r["monto_pendiente"]
        for d in r["descuentos"]:
            clave = f"{d['tipo']} N° {d['cuenta']}"
            aviso["cuentas"][clave] = aviso["cuentas"].get(clave, Decimal(0)) + d["monto"]
    avisos = []
    for rut in sorted(por_rut):
        a = por_rut[rut]
        cuentas = "; ".join(f"{cuenta}: {pesos(monto)}" for cuenta, monto in a["cuentas"].items())
        resoluciones = ", ".join(a["resoluciones"])
        texto = (f"Estimado/a {a['nombre']}: la Tesorería General de la República informó a Banco Genérico la "
                 f"retención de fondos por la(s) resolución(es) N° {resoluciones} (expediente(s) "
                 f"{', '.join(a['expedientes'])}). Corresponde retener {pesos(a['descontado'])} de sus productos "
                 f"bancarios ({cuentas}).")
        if a["pendiente"] > 0:
            texto += f" Queda un saldo de la deuda por {pesos(a['pendiente'])} que no alcanzó a cubrirse."
        texto += " Para aclaraciones, comuníquese con la Tesorería Regional que emitió la resolución."
        avisos.append({**a, "cuentas": cuentas, "resoluciones": resoluciones, "texto": texto})
    return avisos


def construir_excel(avisos: list[dict], informe: str) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Avisos"
    columnas = ["RUT", "Cliente", "N° resolución", "Monto a retener", "Saldo pendiente de la deuda",
                "Cuentas afectadas", "Texto del aviso"]
    _encabezado(hoja, 1, columnas)
    for fila, a in enumerate(avisos, start=2):
        for columna, valor in enumerate([a["rut"], a["nombre"], a["resoluciones"], a["descontado"], a["pendiente"],
                                         a["cuentas"], a["texto"]], start=1):
            celda = hoja.cell(fila, columna, valor)
            celda.alignment = Alignment(vertical="top", wrap_text=columna in (2, 3, 6, 7))
            if columna in (4, 5):
                celda.number_format = FORMATO_PESOS
    if not avisos:
        hoja.cell(2, 1, "Ningún cliente tiene descuento en este informe: no hay avisos que enviar.")
    hoja.freeze_panes = "C2"
    _anchos(hoja, [14, 30, 18, 16, 18, 48, 90])
    nota = libro.create_sheet("Informe")
    nota["A1"], nota["B1"] = "Informe de origen", informe
    nota["A2"], nota["B2"] = "Avisos a generar", len(avisos)
    nota["A3"] = "El sistema no envía correos: esta lista la despacha el banco por sus canales."
    _anchos(nota, [22, 50])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def generar(conexion: Connection, id_archivo: int) -> tuple[bytes, str]:
    datos = recopilar(conexion, id_archivo)
    nombre = datos["archivo"]["nombre_archivo"]
    return construir_excel(armar_avisos(datos["cruce"]), nombre), f"avisos_clientes_{nombre.rsplit('.', 1)[0]}.xlsx"
