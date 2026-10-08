from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_responde():
    respuesta = client.get("/api/health")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_conexion_base_datos():
    """Requiere SQL Server con los scripts de database/ ejecutados."""
    respuesta = client.get("/api/health/db")
    assert respuesta.status_code == 200, respuesta.json()
    assert respuesta.json()["roles"] == 4
