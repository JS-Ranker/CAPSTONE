"""Genera un CSV de muestra en el formato que carga el ETL de Pentaho (Base de datos/*.ktr).

Cada fila es un oficio de embargo de la TGR, con las 21 columnas que lee
`transformacion_carga.ktr` (CSV -> stg.casos_tgr), en el mismo orden. Incluye casos válidos y
casos de borde para cada regla de `Normalizar_TGR.ktr` (stg -> core.casos_tgr), y escribe
`esperado.json` con el resultado que debería tener cada fila, como referencia para las pruebas.

Uso, desde la carpeta backend/:
    python scripts/generar_muestra_tgr.py              # escribe en ../data/muestra_tgr
    python scripts/generar_muestra_tgr.py --validos 40

Con la misma semilla el resultado es siempre el mismo. Los datos son ficticios: los RUT van entre
40.000.000 y 49.999.999, fuera de los rangos asignados hoy a personas y empresas.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

CARPETA_SALIDA = Path(__file__).resolve().parents[2] / "data" / "muestra_tgr"
FECHA_LOTE = date(2026, 10, 12)

# Orden y nombres de transformacion_carga.ktr. El ETL lee por posición.
COLUMNAS = (
    "NOMBRE DOCUMENTO", "RUT", "DV", "ID DEMANDA*", "N° Resolución", "NOMBRE CLIENTE",
    "MONTO SOLICITADO", "SALDO", "TIPO EMBARGO", "EXPEDIENTE", "FECHA INGRESO CASILLA",
    "TESORERIA", "FECHA OFICIO", "MULTIPLES ROLES", "REVISION MANUAL", "CAMPOS FALTANTES OCR",
    "ENTIDAD BANCARIA", "id_correo", "remitente", "asunto", "RUTA DOCUMENTO",
)

NOMBRES = ("CAMILA", "JAVIERA", "VALENTINA", "CATALINA", "FERNANDA", "MATÍAS", "BENJAMÍN",
           "SEBASTIÁN", "DIEGO", "NICOLÁS", "FRANCISCO", "CONSTANZA", "IGNACIO", "PAULA")
APELLIDOS = ("GONZÁLEZ", "MUÑOZ", "ROJAS", "DÍAZ", "PÉREZ", "SOTO", "CONTRERAS", "SILVA",
             "MARTÍNEZ", "SEPÚLVEDA", "MORALES", "RODRÍGUEZ", "LÓPEZ", "FUENTES", "ARAYA")
# (tesorería, localidad del rol). Calzan con la expresión de Separar_Tesoreria.
TESORERIAS = (
    ("TESORERÍA REGIONAL DE SANTIAGO", "SANTIAGO"),
    ("TESORERÍA REGIONAL DE VALPARAÍSO", "VALPARAÍSO"),
    ("TESORERÍA REGIONAL DEL BIOBÍO", "CONCEPCIÓN"),
    ("TESORERÍA PROVINCIAL DE TALAGANTE", "TALAGANTE"),
    ("TESORERÍA PROVINCIAL DEL MAIPO", "SAN BERNARDO"),
    ("TESORERIA REGIONAL DE ANTOFAGASTA", "ANTOFAGASTA"),  # sin tilde: el ETL acepta ambas
)
TIPOS_EMBARGO = ("RETENCIÓN", "EMBARGO")
REMITENTE = "notificaciones@tgr.cl"

CARGA, RECHAZO_INDICADOR, RECHAZO_LLAVE, DUPLICADO = (
    "Carga en core.casos_tgr",
    "Rechazado: indicador distinto de SI/NO (Validar_Indicadores)",
    "Rechazado: llave inválida (Validar_Llave_Caso)",
    "Descartado: duplicado de RUT, DV, rol y fecha de ingreso (Detectar_Duplicados)",
)


def digito_verificador(rut: int) -> str:
    """DV por módulo 11, igual que Validar_RUT_DV."""
    suma, multiplicador = 0, 2
    for cifra in reversed(str(rut)):
        suma += int(cifra) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resultado = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resultado, str(resultado))


def caso_valido(azar: random.Random, numero: int) -> dict[str, str]:
    rut = azar.randint(40_000_000, 49_999_999)
    tesoreria, localidad = azar.choice(TESORERIAS)
    ingreso = FECHA_LOTE - timedelta(days=azar.randint(0, 3))
    oficio = ingreso - timedelta(days=azar.randint(2, 20))
    monto = azar.randint(50, 8_000) * 1_000
    mensaje = f"<{FECHA_LOTE:%Y%m%d}.{numero:04d}@tgr.cl>"
    return {
        "NOMBRE DOCUMENTO": f"{FECHA_LOTE:%Y%m%d}",  # transformacion_carga.ktr lo lee como fecha yyyyMMdd
        "RUT": str(rut),
        "DV": digito_verificador(rut),
        "ID DEMANDA*": str(azar.randint(100_000, 999_999)),
        "N° Resolución": str(azar.randint(10_000, 99_999)),
        "NOMBRE CLIENTE": f"{azar.choice(NOMBRES)} {azar.choice(APELLIDOS)} {azar.choice(APELLIDOS)}",
        "MONTO SOLICITADO": str(monto),
        "SALDO": str(azar.choice((0, 0, 0, azar.randint(1, monto // 1_000) * 1_000))),
        "TIPO EMBARGO": azar.choice(TIPOS_EMBARGO),
        "EXPEDIENTE": f"{azar.randint(100, 99_999)}-{azar.randint(2019, 2026)} {localidad}",
        "FECHA INGRESO CASILLA": f"{ingreso:%d-%m-%Y}",
        "TESORERIA": tesoreria,
        "FECHA OFICIO": f"{oficio:%d-%m-%Y}",
        "MULTIPLES ROLES": "NO",
        "REVISION MANUAL": "NO",
        "CAMPOS FALTANTES OCR": "",
        "ENTIDAD BANCARIA": "BANCO GENÉRICO",
        "id_correo": mensaje,
        "remitente": REMITENTE,
        "asunto": f"Oficio de {azar.choice(TIPOS_EMBARGO).lower()} - Demanda {numero}",
        "RUTA DOCUMENTO": f"documentos/{FECHA_LOTE:%Y%m%d}/oficio_{numero:04d}.pdf",
    }


def casos_de_borde(azar: random.Random, base: list[dict[str, str]]) -> list[tuple[dict[str, str], str, str]]:
    """Una fila por regla del ETL: (fila, resultado esperado, qué prueba)."""
    def nuevo(numero: int, **cambios: str) -> dict[str, str]:
        return {**caso_valido(azar, numero), **cambios}

    mal_dv = nuevo(901)
    mal_dv["DV"] = "0" if mal_dv["DV"] != "0" else "1"
    rut_k = next(r for r in iter(lambda: azar.randint(40_000_000, 49_999_999), None) if digito_verificador(r) == "K")
    return [
        (mal_dv, RECHAZO_LLAVE, "DV no calza con el RUT"),
        (nuevo(903, RUT=str(rut_k), DV="k"), CARGA, "DV 'k' en minúscula (Normalizacion lo pasa a mayúscula)"),
        (nuevo(904, EXPEDIENTE="ROL SIN NÚMERO"), RECHAZO_LLAVE, "expediente sin formato número-año localidad"),
        (nuevo(905, **{"FECHA INGRESO CASILLA": ""}), RECHAZO_LLAVE, "sin fecha de ingreso"),
        (nuevo(906, **{"MULTIPLES ROLES": "QUIZÁS"}), RECHAZO_INDICADOR, "indicador de múltiples roles inválido"),
        (nuevo(907, **{"REVISION MANUAL": ""}), RECHAZO_INDICADOR, "revisión manual vacía"),
        (nuevo(908, **{"MULTIPLES ROLES": "SÍ"}), CARGA, "'SÍ' con tilde"),
        (nuevo(909, **{"REVISION MANUAL": "SI", "CAMPOS FALTANTES OCR": "FECHA OFICIO, N° RESOLUCIÓN",
                       "FECHA OFICIO": "", "N° Resolución": ""}), CARGA, "OCR incompleto, marcado para revisión"),
        (nuevo(910, EXPEDIENTE="  1532 - 2024   valparaíso ", TESORERIA=" tesorería regional de valparaíso "),
         CARGA, "espacios y minúsculas (Normalizacion los limpia)"),
        ({**base[0]}, DUPLICADO, "copia exacta de la primera fila"),
        ({**base[1], "id_correo": "<reenvio.0002@tgr.cl>", "asunto": "RV: " + base[1]["asunto"]},
         DUPLICADO, "mismo caso reenviado en otro correo"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validos", type=int, default=24, help="filas válidas (por defecto 24)")
    parser.add_argument("--semilla", type=int, default=20261012)
    parser.add_argument("--salida", type=Path, default=CARPETA_SALIDA)
    args = parser.parse_args()

    azar = random.Random(args.semilla)
    validos = [caso_valido(azar, numero) for numero in range(1, args.validos + 1)]
    filas = [(fila, CARGA, "caso válido") for fila in validos] + casos_de_borde(azar, validos)

    args.salida.mkdir(parents=True, exist_ok=True)
    archivo = args.salida / f"resultado_tgr_{FECHA_LOTE:%Y%m%d}.csv"
    # utf-8-sig: el .ktr espera el BOM (su primera columna es "﻿NOMBRE DOCUMENTO").
    with archivo.open("w", encoding="utf-8-sig", newline="") as salida:
        escritor = csv.DictWriter(salida, fieldnames=COLUMNAS, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        escritor.writeheader()
        escritor.writerows(fila for fila, _, _ in filas)

    esperado = [
        {"fila": numero, "rut": f"{fila['RUT']}-{fila['DV']}", "expediente": fila["EXPEDIENTE"],
         "resultado": resultado, "prueba": prueba}
        for numero, (fila, resultado, prueba) in enumerate(filas, start=2)  # fila 1 = encabezado
    ]
    resumen = {r: sum(1 for e in esperado if e["resultado"] == r)
               for r in (CARGA, RECHAZO_INDICADOR, RECHAZO_LLAVE, DUPLICADO)}
    (args.salida / "esperado.json").write_text(
        json.dumps({"archivo": archivo.name, "resumen": resumen, "filas": esperado},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{archivo} ({len(filas)} filas)")
    for resultado, cantidad in resumen.items():
        print(f"  {cantidad:3d}  {resultado}")


if __name__ == "__main__":
    main()
