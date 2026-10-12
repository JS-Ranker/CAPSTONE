"""Ejecuta el ETL de casos TGR sobre un CSV y muestra el resumen (CSV -> stg -> core.casos_tgr).

Uso, desde la carpeta backend/:
    python scripts/ejecutar_etl.py ../data/muestra_tgr/resultado_tgr_20261012.csv

Escribe en la base configurada en backend/.env. Volver a cargar el mismo archivo no duplica casos:
sus filas quedan como "Duplicado".
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine  # noqa: E402
from app.modulos.etl.carga import ErrorFormatoCsv, ejecutar  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path, help="archivo resultado_tgr_*.csv")
    args = parser.parse_args()
    if not args.csv.is_file():
        print(f"No existe el archivo {args.csv}", file=sys.stderr)
        return 1
    try:
        with engine.connect() as conexion:
            resumen = ejecutar(conexion, args.csv)
    except ErrorFormatoCsv as error:
        print(f"No se cargó {args.csv.name}: {error}", file=sys.stderr)
        return 1
    print(f"Ejecución #{resumen.id_ejecucion} - {args.csv.name}: {resumen.filas_leidas} filas leídas")
    print(f"  {resumen.cargadas:4d} cargadas en core.casos_tgr")
    print(f"  {resumen.rechazadas:4d} rechazadas (motivo en etl.resultados)")
    print(f"  {resumen.duplicadas:4d} duplicadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
