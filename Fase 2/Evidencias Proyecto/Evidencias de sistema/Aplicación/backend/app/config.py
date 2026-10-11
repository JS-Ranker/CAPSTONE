"""Configuración leída desde variables de entorno (archivo backend/.env)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _ruta(variable: str, por_defecto: str) -> Path:
    """Ruta de una variable de entorno; las relativas se resuelven desde backend/, no desde el directorio actual."""
    ruta = Path(os.getenv(variable) or por_defecto)
    return ruta if ruta.is_absolute() else (BACKEND_DIR / ruta).resolve()


@dataclass(frozen=True)
class Settings:
    db_server: str = os.getenv("DB_SERVER", "localhost")
    db_name: str = os.getenv("DB_NAME", "TTDH_Automation")
    db_driver: str = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    db_trusted_connection: bool = os.getenv("DB_TRUSTED_CONNECTION", "yes").lower() == "yes"
    db_user: str = os.getenv("DB_USER", "")
    db_password: str = os.getenv("DB_PASSWORD", "")
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "tesseract")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Recepción de documentos (RF01). data/entrada/ está excluida del repositorio.
    almacen_documentos: Path = _ruta("ALMACEN_DOCUMENTOS", "../data/entrada/documentos")
    tamano_maximo_mb: int = int(os.getenv("TAMANO_MAXIMO_MB", "20"))
    sftp_directorio: Path = _ruta("SFTP_DIRECTORIO", "../data/entrada/sftp")
    imap_servidor: str = os.getenv("IMAP_SERVIDOR", "")
    imap_puerto: int = int(os.getenv("IMAP_PUERTO", "993"))
    imap_usuario: str = os.getenv("IMAP_USUARIO", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")
    imap_carpeta: str = os.getenv("IMAP_CARPETA", "INBOX")
    # Los remitentes autorizados se administran desde la pantalla (tabla Remitentes_Autorizados).


settings = Settings()
