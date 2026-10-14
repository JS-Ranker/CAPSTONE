"""Genera saldos bancarios de PRUEBA para los mismos deudores de los PDF TGR.

Entrada prioritaria: documentos_generados/extraccion_tgr.csv (del generador unificado).
Si no existe: lee directamente documentos_generados/TGR_PRUEBA_*.pdf.
Salida: documentos_generados/saldos_deudores.csv (rut;dv;nombre_cliente;tipo_cta;monto).

Uso:
    python generar_saldos_bancarios_tgr.py
Dependencia para leer PDF directamente: pip install pymupdf
"""
from __future__ import annotations

import csv
import random
import re
from pathlib import Path

# ============================= CONFIGURACIÓN =============================
CARPETA = Path(__file__).resolve().parent / "documentos_generados"
EXTRACCION = CARPETA / "extraccion_tgr.csv"
SALIDA = CARPETA / "saldos_deudores.csv"

TIPOS_CUENTA = ("cuenta_rut", "corriente", "chequera_ele", "ahorro")
MIN_CUENTAS = 1
MAX_CUENTAS = 4
SALDO_MINIMO = 0
SALDO_MAXIMO = 15_000_000
# None: nuevos saldos en cada ejecución. Un número fijo: mismo resultado reproducible.
SEMILLA = None
COLUMNAS = ("rut", "dv", "nombre_cliente", "tipo_cta", "monto")


def calcular_dv(rut: str) -> str:
    suma = sum(int(d) * (2 + i % 6) for i, d in enumerate(reversed(rut)))
    resultado = 11 - suma % 11
    return "0" if resultado == 11 else "K" if resultado == 10 else str(resultado)


def validar_cliente(rut: str, dv: str, nombre: str, origen: str) -> dict:
    rut = re.sub(r"[.\s]", "", str(rut))
    dv = str(dv).strip().upper()
    nombre = " ".join(str(nombre).strip().split())
    if not rut.isdigit() or not nombre or calcular_dv(rut) != dv:
        raise ValueError(f"RUT, DV o nombre inválidos en {origen}: {rut}-{dv} / {nombre}")
    return {"rut": rut, "dv": dv, "nombre_cliente": nombre}


def consolidar(clientes: list[dict]) -> list[dict]:
    # Un deudor puede tener más de un oficio: se generan cuentas UNA SOLA VEZ por RUT.
    por_rut = {}
    for cliente in clientes:
        rut = cliente["rut"]
        if rut in por_rut and por_rut[rut] != cliente:
            raise ValueError(f"El RUT {rut} tiene datos personales contradictorios")
        por_rut[rut] = cliente
    if not por_rut:
        raise ValueError("No se encontraron deudores válidos")
    return sorted(por_rut.values(), key=lambda c: int(c["rut"]))


def leer_extraccion_csv() -> list[dict]:
    clientes = []
    with EXTRACCION.open("r", encoding="utf-8-sig", newline="") as f:
        muestra = f.read(4096)
        f.seek(0)
        separador = ";" if muestra.count(";") >= muestra.count(",") else ","
        lector = csv.DictReader(f, delimiter=separador)
        lector.fieldnames = [x.strip().upper() for x in (lector.fieldnames or [])]
        necesarios = {"RUT", "DV", "NOMBRE CLIENTE"}
        if not necesarios.issubset(lector.fieldnames):
            raise ValueError(f"En {EXTRACCION} faltan estas columnas: {necesarios - set(lector.fieldnames)}")
        for num, fila in enumerate(lector, start=2):
            rut, dv, nombre = ((fila.get(c) or "").strip() for c in ("RUT", "DV", "NOMBRE CLIENTE"))
            if not (rut and dv and nombre):
                raise ValueError(f"Faltan datos de identidad en {EXTRACCION.name}, fila {num}; revisar extracción del PDF")
            clientes.append(validar_cliente(rut, dv, nombre, f"{EXTRACCION.name}:{num}"))
    return consolidar(clientes)


def leer_pdf() -> list[dict]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("Para leer PDF directamente instala: pip install pymupdf") from exc
    archivos = sorted(CARPETA.glob("TGR_PRUEBA_*.pdf"))
    if not archivos:
        raise FileNotFoundError(f"No hay extraccion_tgr.csv ni PDF TGR_PRUEBA_*.pdf en {CARPETA}")
    # Captura el nombre en la línea inmediatamente anterior al RUT.
    patron = re.compile(r"(?:^|\n)\s*([^\n,]+?)\s*,\s*RUT\s*:\s*([\d.]+)\s*-\s*([\dKk])\b", re.I)
    clientes = []
    for pdf in archivos:
        with fitz.open(pdf) as doc:
            texto = doc[0].get_text(sort=True)
        encontrado = patron.search(texto)
        if not encontrado:
            raise ValueError(f"No se pudo extraer la identidad desde {pdf.name}")
        nombre, rut, dv = encontrado.groups()
        clientes.append(validar_cliente(rut, dv, nombre, pdf.name))
    return consolidar(clientes)


def generar_saldos(clientes: list[dict]) -> list[dict]:
    if not (1 <= MIN_CUENTAS <= MAX_CUENTAS <= len(TIPOS_CUENTA)):
        raise ValueError("MIN_CUENTAS y MAX_CUENTAS deben estar entre 1 y 4")
    if SALDO_MINIMO < 0 or SALDO_MAXIMO < SALDO_MINIMO:
        raise ValueError("El rango de saldos no es válido")
    aleatorio = random.Random(SEMILLA)
    filas = []
    for cliente in clientes:
        for tipo in aleatorio.sample(TIPOS_CUENTA, aleatorio.randint(MIN_CUENTAS, MAX_CUENTAS)):
            filas.append({**cliente, "tipo_cta": tipo, "monto": aleatorio.randint(SALDO_MINIMO, SALDO_MAXIMO)})
    return filas


def main() -> None:
    if EXTRACCION.is_file():
        print(f"Origen: {EXTRACCION} (datos extraídos de los PDF)")
        clientes = leer_extraccion_csv()
    else:
        print("No se encontró el CSV de extracción; leyendo los PDF directamente")
        clientes = leer_pdf()
    filas = generar_saldos(clientes)
    CARPETA.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS, delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"Deudores únicos: {len(clientes)}")
    print(f"Cuentas generadas: {len(filas)}")
    print(f"Archivo generado: {SALIDA}")
    print("IMPORTANTE: 'monto' es saldo bancario inventado, NO deuda TGR.")


if __name__ == "__main__":
    main()
