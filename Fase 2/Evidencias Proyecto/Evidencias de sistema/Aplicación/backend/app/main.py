"""API REST de TTDH Automation.

Ejecutar desde la carpeta backend/:  uvicorn app.main:app --reload
Documentación interactiva:            http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .db import engine

app = FastAPI(title="TTDH Automation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Verifica que la API esté en ejecución."""
    return {"estado": "ok", "servicio": "TTDH Automation API"}


@app.get("/api/health/db")
def health_db():
    """Verifica la conexión con SQL Server y que el esquema esté creado."""
    try:
        with engine.connect() as conn:
            roles = conn.execute(text("SELECT COUNT(*) FROM dbo.Roles")).scalar_one()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Sin conexión a la base de datos: {exc.__class__.__name__}") from exc
    return {"estado": "ok", "base_datos": settings.db_name, "roles": roles}
