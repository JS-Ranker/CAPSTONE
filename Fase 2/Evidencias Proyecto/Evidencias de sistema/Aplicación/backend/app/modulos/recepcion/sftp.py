"""Canal SFTP (CU02 1b): lee el directorio donde el servidor SFTP deposita los documentos de la TGR.

Cada archivo leído se mueve a `procesados/AAAA-MM-DD/` (registrado) o a `rechazados/AAAA-MM-DD/` (tipo no
permitido, vacío, demasiado grande o ya recibido), así no se vuelve a leer y el analista puede revisar los
rechazados. Si falla el registro (por ejemplo, sin base de datos), el archivo queda en su lugar para la
próxima revisión; volver a procesarlo es seguro porque los duplicados se detectan por su huella.
"""
import time
from datetime import date
from pathlib import Path

from sqlalchemy import Connection

from ... import bitacora
from ...db import transaccion
from .registro import SFTP, ResumenCanal, recibir_documento, resumen_para_bitacora

PROCESADOS, RECHAZADOS = "procesados", "rechazados"
REVISION_SFTP = "Revisión de directorio SFTP"  # acción de bitácora
_TEMPORALES = (".part", ".filepart", ".tmp", ".crdownload")


def archivos_listos(directorio: Path, antiguedad_minima: float) -> list[Path]:
    """Archivos del directorio (sin subcarpetas) que ya terminaron de copiarse."""
    limite = time.time() - antiguedad_minima
    return sorted(
        ruta for ruta in directorio.iterdir()
        if ruta.is_file()
        and not ruta.name.startswith((".", "~"))
        and not ruta.name.lower().endswith(_TEMPORALES)
        and ruta.stat().st_mtime <= limite
    )


def revisar_directorio(
    conexion: Connection,
    directorio: Path,
    *,
    almacen: Path,
    tamano_maximo: int,
    antiguedad_minima: float = 60,
) -> ResumenCanal:
    """Registra los archivos del directorio SFTP. `antiguedad_minima`: segundos sin cambios antes de leer uno."""
    resumen = ResumenCanal()
    if not directorio.is_dir():
        raise FileNotFoundError(f"No existe el directorio SFTP {directorio}")

    listos = archivos_listos(directorio, antiguedad_minima)
    resumen.omitidos = sum(1 for ruta in directorio.iterdir() if ruta.is_file()) - len(listos)
    for ruta in listos:
        try:
            resultado = recibir_documento(conexion, ruta.read_bytes(), ruta.name, SFTP,
                                          almacen=almacen, tamano_maximo=tamano_maximo)
        except Exception as exc:  # noqa: BLE001 - un archivo con problemas no debe detener la revisión
            resumen.fallidos += 1
            resumen.errores.append(f"{ruta.name}: {exc.__class__.__name__}")
            continue
        if resultado.aceptado:
            resumen.registrados += 1
            _mover(ruta, directorio / PROCESADOS)
        else:
            resumen.rechazados += 1
            resumen.errores.append(f"{ruta.name}: {resultado.motivo.value}. {resultado.detalle}".strip())
            _mover(ruta, directorio / RECHAZADOS)

    with transaccion(conexion):  # deja constancia de la revisión (la pantalla de ingesta muestra la última)
        bitacora.registrar(conexion, REVISION_SFTP, resumen_para_bitacora(resumen))
    return resumen


def _mover(ruta: Path, carpeta: Path) -> Path:
    """Mueve el archivo a carpeta/AAAA-MM-DD/ sin sobrescribir otro con el mismo nombre."""
    destino_dir = carpeta / date.today().isoformat()
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / ruta.name
    contador = 1
    while destino.exists():
        destino = destino_dir / f"{ruta.stem}_{contador}{ruta.suffix}"
        contador += 1
    return ruta.replace(destino)
