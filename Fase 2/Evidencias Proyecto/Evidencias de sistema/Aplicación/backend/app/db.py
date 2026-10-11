"""Conexión a SQL Server mediante SQLAlchemy + pyodbc."""
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import URL

from .config import settings


def _url() -> URL:
    query = {"driver": settings.db_driver, "TrustServerCertificate": "yes"}
    if settings.db_trusted_connection:
        query["Trusted_Connection"] = "yes"
        return URL.create("mssql+pyodbc", host=settings.db_server, database=settings.db_name, query=query)
    return URL.create(
        "mssql+pyodbc",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_server,
        database=settings.db_name,
        query=query,
    )


engine = create_engine(_url(), pool_pre_ping=True, fast_executemany=True)


@contextmanager
def transaccion(conexion: Connection) -> Iterator[Connection]:
    """Transacción corta que se confirma al salir del bloque y se revierte si hay un error.

    Si la conexión ya está dentro de una transacción externa (las pruebas, que la revierten al terminar),
    usa un punto de guardado. Por eso toda consulta debe ir dentro de un bloque `with transaccion(...)`:
    una consulta suelta abre una transacción implícita y los bloques siguientes no se confirmarían.
    """
    bloque = conexion.begin_nested() if conexion.in_transaction() else conexion.begin()
    with bloque:
        yield conexion
