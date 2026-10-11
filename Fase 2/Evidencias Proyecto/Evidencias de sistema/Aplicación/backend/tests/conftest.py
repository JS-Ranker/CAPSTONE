"""Fixtures compartidas. Las pruebas que usan la base de datos corren dentro de una transacción que se revierte
al final, así no dejan datos en SQL Server (la Bitácora de Trazabilidad no permite borrar filas)."""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import BACKEND_DIR
from app.db import engine

SIMULADOS = BACKEND_DIR.parent / "data" / "simulados"


@pytest.fixture
def conexion():
    """Conexión a SQL Server en una transacción que se revierte. Se omite la prueba si no hay base de datos."""
    try:
        conexion = engine.connect()
    except SQLAlchemyError:
        pytest.skip("SQL Server no disponible (scripts de 'Base de datos' sin ejecutar)")
    transaccion = conexion.begin()
    try:
        columnas = conexion.execute(text("SELECT COL_LENGTH('dbo.Archivos_TGR', 'hash_sha256')")).scalar_one()
        if columnas is None:
            pytest.skip("Falta ejecutar 'Base de datos/04_recepcion.sql'")
        # Cada prueba parte sin archivos, aunque la base de desarrollo ya tenga datos (si no, los simulados
        # se rechazarían como duplicados). El borrado ocurre dentro de la transacción y se revierte al final.
        for tabla in ("Analisis_IA_Anomalias", "Conciliacion_Banco", "Registros_TGR", "Archivos_TGR"):
            conexion.execute(text(f"DELETE FROM dbo.{tabla}"))
        yield conexion
    finally:
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def almacen(tmp_path) -> Path:
    return tmp_path / "almacen"


def simulado(nombre: str) -> Path:
    """Ruta de un archivo de data/simulados (estructurados/ o no_estructurados/)."""
    for carpeta in ("estructurados", "no_estructurados"):
        ruta = SIMULADOS / carpeta / nombre
        if ruta.is_file():
            return ruta
    raise FileNotFoundError(nombre)
