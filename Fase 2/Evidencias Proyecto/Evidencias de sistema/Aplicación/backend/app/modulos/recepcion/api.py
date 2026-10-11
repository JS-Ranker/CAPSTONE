"""Endpoints de recepción (RF01, CU02): carga web de documentos y consulta de los lotes recientes.

Pendiente: la plataforma aún no tiene inicio de sesión (CU01, RF09). Cuando exista, la carga web debe
exigir el rol Analista o Administrador y registrar en la bitácora al usuario que carga el documento.
"""
import imaplib
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import Connection, text

from ...config import settings
from ...db import engine, transaccion
from .correo import REVISION_CORREO, Buzon, conectar_imap, revisar_buzon
from .pendientes import buscar_pendiente, extraer_pendiente, procesar_pendientes
from .registro import (
    CORREO, PENDIENTE_EXTRACCION, SFTP, WEB, MotivoRechazo, ResumenCanal, recibir_documento, resumen_para_bitacora,
)
from .sftp import REVISION_SFTP, revisar_directorio

ANTIGUEDAD_MINIMA_MANUAL = 10  # segundos: al forzar la lectura SFTP se esperan menos que en la revisión programada

router = APIRouter(prefix="/api/recepcion", tags=["Recepción"])

CODIGOS_RECHAZO = {
    MotivoRechazo.TIPO_NO_PERMITIDO: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    MotivoRechazo.VACIO: status.HTTP_400_BAD_REQUEST,
    MotivoRechazo.DEMASIADO_GRANDE: status.HTTP_413_CONTENT_TOO_LARGE,
    MotivoRechazo.DUPLICADO: status.HTTP_409_CONFLICT,
}
COLUMNAS_PUBLICAS = (
    "id_archivo, nombre_archivo, canal_origen, remitente, asunto_correo, fecha_correo, tipo_documento, "
    "fecha_recepcion, estado_archivo, total_registros, confianza_extraccion"
)  # sin la ruta interna del almacén ni la huella


# --- Dependencias (las pruebas las reemplazan para no escribir en la base real) ---
def obtener_conexion() -> Iterator[Connection]:
    with engine.connect() as conexion:
        yield conexion


def obtener_almacen() -> Path:
    return settings.almacen_documentos


def _extraer_en_segundo_plano(id_archivo: int) -> None:
    with engine.connect() as conexion:
        documento = buscar_pendiente(conexion, id_archivo)
        if documento:
            extraer_pendiente(conexion, documento, settings.almacen_documentos)


def obtener_extractor() -> Callable[[int], None]:
    return _extraer_en_segundo_plano


def _procesar_pendientes_en_segundo_plano() -> None:
    with engine.connect() as conexion:
        procesar_pendientes(conexion, settings.almacen_documentos)


def obtener_procesador_pendientes() -> Callable[[], None]:
    return _procesar_pendientes_en_segundo_plano


def correo_configurado() -> bool:
    return bool(settings.imap_servidor and settings.imap_usuario and settings.remitentes_autorizados)


def obtener_buzon() -> Callable[[], AbstractContextManager[Buzon]]:
    """Fábrica de la conexión a la casilla (las pruebas la reemplazan por un buzón en memoria)."""
    if not correo_configurado():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="La casilla de correo no está configurada (IMAP_* y REMITENTES_AUTORIZADOS en .env).")
    return lambda: conectar_imap(settings.imap_servidor, settings.imap_puerto, settings.imap_usuario,
                                 settings.imap_password, settings.imap_carpeta)


def obtener_directorio_sftp() -> Path:
    return settings.sftp_directorio


# --- Endpoints ---
@router.post("/archivos", status_code=status.HTTP_201_CREATED)
def cargar_archivo(
    tareas: BackgroundTasks,
    archivo: UploadFile = File(..., description="Excel, CSV, TXT, PDF o imagen JPG/PNG de la TGR"),
    conexion: Connection = Depends(obtener_conexion),
    almacen: Path = Depends(obtener_almacen),
    extractor: Callable[[int], None] = Depends(obtener_extractor),
):
    """Carga manual de un documento TGR (CU02 1a). Los PDF e imágenes se normalizan en segundo plano."""
    maximo = settings.tamano_maximo_mb * 1024 * 1024
    contenido = archivo.file.read(maximo + 1)  # un byte de más basta para saber que excede el máximo
    resultado = recibir_documento(conexion, contenido, archivo.filename or "", WEB,
                                  almacen=almacen, tamano_maximo=maximo)
    if not resultado.aceptado:
        raise HTTPException(
            status_code=CODIGOS_RECHAZO[resultado.motivo],
            detail={
                "motivo": resultado.motivo.name,
                "mensaje": f"{resultado.motivo.value}. {resultado.detalle}".strip(),
                "id_archivo_existente": resultado.id_archivo_existente,
            },
        )

    documento = resultado.documento
    if documento.estado_archivo == PENDIENTE_EXTRACCION:
        tareas.add_task(extractor, documento.id_archivo)
    return {
        "id_archivo": documento.id_archivo,
        "nombre_archivo": documento.nombre_archivo,
        "canal_origen": documento.canal_origen,
        "tipo_documento": documento.tipo_documento,
        "estado_archivo": documento.estado_archivo,
    }


@router.get("/archivos")
def listar_archivos(
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    conexion: Connection = Depends(obtener_conexion),
):
    """Lotes recientes (CU02 paso 7), del más nuevo al más antiguo."""
    with transaccion(conexion):
        total = conexion.execute(text("SELECT COUNT(*) FROM dbo.Archivos_TGR")).scalar_one()
        filas = conexion.execute(
            text(f"SELECT {COLUMNAS_PUBLICAS} FROM dbo.Archivos_TGR "
                 "ORDER BY fecha_recepcion DESC, id_archivo DESC "
                 "OFFSET :desplazamiento ROWS FETCH NEXT :limite ROWS ONLY"),
            {"desplazamiento": desplazamiento, "limite": limite},
        ).mappings().all()
    return {"total": total, "limite": limite, "desplazamiento": desplazamiento, "archivos": [dict(f) for f in filas]}


@router.get("/archivos/{id_archivo}")
def obtener_archivo(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    with transaccion(conexion):
        fila = conexion.execute(
            text(f"SELECT {COLUMNAS_PUBLICAS} FROM dbo.Archivos_TGR WHERE id_archivo = :id"), {"id": id_archivo}
        ).mappings().one_or_none()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    return dict(fila)


@router.get("/estado")
def estado_recepcion(
    conexion: Connection = Depends(obtener_conexion),
    directorio_sftp: Path = Depends(obtener_directorio_sftp),
):
    """Estado de la recepción automática (panel "Recepción automática" de la pantalla de ingesta)."""
    with transaccion(conexion):
        ultimas = dict(conexion.execute(
            text("SELECT accion_ejecutada, MAX(timestamp_accion) FROM dbo.Bitacora_Trazabilidad "
                 "WHERE accion_ejecutada IN (:correo, :sftp) GROUP BY accion_ejecutada"),
            {"correo": REVISION_CORREO, "sftp": REVISION_SFTP},
        ).all())
        hoy = dict(conexion.execute(
            text("SELECT canal_origen, COUNT(*) FROM dbo.Archivos_TGR "
                 "WHERE CAST(fecha_recepcion AS DATE) = CAST(SYSDATETIME() AS DATE) GROUP BY canal_origen"),
        ).all())
        pendientes = conexion.execute(
            text("SELECT COUNT(*) FROM dbo.Archivos_TGR WHERE estado_archivo = :estado"),
            {"estado": PENDIENTE_EXTRACCION},
        ).scalar_one()
    return {
        "correo": {"configurado": correo_configurado(), "ultima_revision": ultimas.get(REVISION_CORREO),
                   "recibidos_hoy": hoy.get(CORREO, 0)},
        "sftp": {"configurado": directorio_sftp.is_dir(), "ultima_revision": ultimas.get(REVISION_SFTP),
                 "recibidos_hoy": hoy.get(SFTP, 0)},
        "web": {"recibidos_hoy": hoy.get(WEB, 0)},
        "pendientes_extraccion": pendientes,
    }


def _respuesta_revision(resumen: ResumenCanal, tareas: BackgroundTasks, procesador: Callable[[], None]) -> dict:
    if resumen.registrados:
        tareas.add_task(procesador)  # normaliza los PDF e imágenes recién recibidos
    return resumen_para_bitacora(resumen)


@router.post("/revisar/correo")
def revisar_correo_ahora(
    tareas: BackgroundTasks,
    conexion: Connection = Depends(obtener_conexion),
    almacen: Path = Depends(obtener_almacen),
    abrir_buzon: Callable[[], AbstractContextManager[Buzon]] = Depends(obtener_buzon),
    procesador: Callable[[], None] = Depends(obtener_procesador_pendientes),
):
    """Lee la casilla de correo en el momento, sin esperar la revisión programada ("Leer correo ahora")."""
    try:
        with abrir_buzon() as buzon:
            resumen = revisar_buzon(conexion, buzon, remitentes_autorizados=settings.remitentes_autorizados,
                                    almacen=almacen, tamano_maximo=settings.tamano_maximo_mb * 1024 * 1024)
    except (imaplib.IMAP4.error, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="No se pudo conectar con la casilla de correo. Revise la configuración.") from exc
    return _respuesta_revision(resumen, tareas, procesador)


@router.post("/revisar/sftp")
def revisar_sftp_ahora(
    tareas: BackgroundTasks,
    conexion: Connection = Depends(obtener_conexion),
    almacen: Path = Depends(obtener_almacen),
    directorio: Path = Depends(obtener_directorio_sftp),
    procesador: Callable[[], None] = Depends(obtener_procesador_pendientes),
):
    """Lee el directorio SFTP en el momento ("Forzar lectura SFTP")."""
    if not directorio.is_dir():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El directorio SFTP no existe.")
    resumen = revisar_directorio(conexion, directorio, almacen=almacen, antiguedad_minima=ANTIGUEDAD_MINIMA_MANUAL,
                                 tamano_maximo=settings.tamano_maximo_mb * 1024 * 1024)
    return _respuesta_revision(resumen, tareas, procesador)
