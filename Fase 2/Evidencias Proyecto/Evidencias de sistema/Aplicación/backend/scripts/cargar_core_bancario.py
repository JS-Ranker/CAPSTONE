"""Carga las cuentas simuladas de Banco Genérico en banco.cuentas (10_cruce.sql) para poder cruzar los informes.

Uso, desde la carpeta backend/:
    python scripts/cargar_core_bancario.py                        # data/simulados/banco_generico/cuentas_core_bancario.csv
    python scripts/cargar_core_bancario.py otra_base.csv

Escribe en la base configurada en backend/.env. Se puede repetir: actualiza el saldo de las cuentas que ya existen.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BACKEND_DIR  # noqa: E402
from app.db import engine  # noqa: E402
from app.modulos.cruce.core_bancario import ErrorCoreBancario, cargar, leer  # noqa: E402

POR_DEFECTO = BACKEND_DIR.parent / "data" / "simulados" / "banco_generico" / "cuentas_core_bancario.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path, nargs="?", default=POR_DEFECTO, help="CSV de cuentas")
    args = parser.parse_args()
    if not args.csv.is_file():
        print(f"No existe el archivo {args.csv}", file=sys.stderr)
        return 1
    try:
        cuentas = leer(args.csv)
    except ErrorCoreBancario as error:
        print(f"No se cargó {args.csv.name}: {error}", file=sys.stderr)
        return 1
    with engine.connect() as conexion:
        resumen = cargar(conexion, cuentas, args.csv.name)
    print(f"{args.csv.name}: {resumen.nuevas} cuentas nuevas, {resumen.actualizadas} actualizadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
