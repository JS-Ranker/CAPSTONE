"""Conexión a SQL Server mediante SQLAlchemy + pyodbc."""
from sqlalchemy import create_engine
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
