"""Fixtures compartidas. Las pruebas que usan la base de datos corren dentro de una transacción que se revierte
al final, así no dejan datos en SQL Server (la Bitácora de Trazabilidad no permite borrar filas)."""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import BACKEND_DIR
from app.db import engine

SIMULADOS = BACKEND_DIR.parent / "data" / "simulados"
# En orden de borrado (las hijas primero). Son de los scripts de Tomás y de 06_etl.sql / 07_revisiones.sql.
TABLAS_ETL = ("etl.revisiones", "etl.resultados", "etl.ejecuciones", "core.casos_tgr", "stg.casos_tgr")


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
        if conexion.execute(text("SELECT OBJECT_ID('dbo.Remitentes_Autorizados', 'U')")).scalar_one() is None:
            pytest.skip("Falta ejecutar 'Base de datos/05_remitentes.sql'")
        # Cada prueba parte sin archivos ni remitentes, aunque la base de desarrollo ya tenga datos (si no, los
        # simulados se rechazarían como duplicados). El borrado ocurre dentro de la transacción y se revierte.
        # Primero las tablas del ETL (si existen), que apuntan a Archivos_TGR.
        for tabla in TABLAS_ETL:
            if conexion.execute(text("SELECT OBJECT_ID(:tabla, 'U')"), {"tabla": tabla}).scalar_one() is not None:
                conexion.execute(text(f"DELETE FROM {tabla}"))
        for tabla in ("Analisis_IA_Anomalias", "Conciliacion_Banco", "Registros_TGR", "Archivos_TGR",
                      "Remitentes_Autorizados"):
            conexion.execute(text(f"DELETE FROM dbo.{tabla}"))
        yield conexion
    finally:
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def conexion_etl(conexion):
    """Conexión sin casos previos (la fixture `conexion` ya vació stg, core y etl). Se omite si faltan tablas."""
    for tabla in TABLAS_ETL:
        if conexion.execute(text("SELECT OBJECT_ID(:tabla, 'U')"), {"tabla": tabla}).scalar_one() is None:
            pytest.skip(f"Falta la tabla {tabla}: ejecutar creacion_db.sql, recepcion_datos_input.sql, "
                        "creacion_tablas.sql, 06_etl.sql y 07_revisiones.sql")
    return conexion


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
