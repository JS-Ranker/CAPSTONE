"""Endpoints de recepción (RF01, CU02): carga web de documentos y consulta de los lotes recientes.

Pendiente: la plataforma aún no tiene inicio de sesión (CU01, RF09). Cuando exista, la carga web debe
exigir el rol Analista o Administrador y registrar en la bitácora al usuario que carga el documento.
"""
import imaplib
import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ...config import settings
from ...db import engine, transaccion
from ..etl.carga import ERROR as ETL_ERROR
from ..etl.carga import PROCESADO as ETL_PROCESADO
from ..etl.carga import ErrorFormatoCsv, es_csv_tgr, procesar_archivo
from ..excepciones.servicio import pendientes_por_informe
from ..extraccion.plantilla import ERROR_EXTRACCION
from .correo import REVISION_CORREO, Buzon, conectar_imap, revisar_buzon
from .documentos import TIPOS_MIME, VISIBLES_EN_NAVEGADOR, DocumentoOriginal, ruta_segura
from .pendientes import buscar_pendiente, extraer_pendiente, procesar_pendientes
from .registro import (
    CORREO, PENDIENTE_EXTRACCION, SFTP, WEB, MotivoRechazo, ResumenCanal, recibir_documento, resumen_para_bitacora,
)
from .remitentes import (
    LARGO_MAXIMO_CORREO, LARGO_MAXIMO_NOMBRE, RemitenteInvalido, agregar_remitente, correos_autorizados,
    listar_remitentes, quitar_remitente,
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
    return bool(settings.imap_servidor and settings.imap_usuario)


def obtener_buzon() -> Callable[[], AbstractContextManager[Buzon]]:
    """Fábrica de la conexión a la casilla (las pruebas la reemplazan por un buzón en memoria)."""
    if not correo_configurado():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="La casilla de correo no está configurada (IMAP_* en backend/.env).")
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

    # Un CSV con el formato TGR pasa por el ETL de inmediato (es rápido). Si su contenido no sirve,
    # el documento igual queda recibido, en estado "Error", y la respuesta lo informa.
    etl, estado = None, documento.estado_archivo
    if documento.tipo_documento == "CSV" and es_csv_tgr(almacen / documento.ruta_original):
        try:
            resumen = procesar_archivo(conexion, documento.id_archivo, almacen)
            etl, estado = asdict(resumen), ETL_PROCESADO
        except ErrorFormatoCsv as exc:
            etl, estado = {"error": str(exc)}, ETL_ERROR
    return {
        "id_archivo": documento.id_archivo,
        "nombre_archivo": documento.nombre_archivo,
        "canal_origen": documento.canal_origen,
        "tipo_documento": documento.tipo_documento,
        "estado_archivo": estado,
        "etl": etl,
    }


@router.get("/archivos")
def listar_archivos(
    limite: int = Query(20, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    conexion: Connection = Depends(obtener_conexion),
):
    """Lotes recientes (CU02 paso 7), del más nuevo al más antiguo."""
    with transaccion(conexion):
        total, con_error = conexion.execute(text(
            "SELECT COUNT(*), COUNT(CASE WHEN estado_archivo IN (:error_extraccion, :error) THEN 1 END) "
            "FROM dbo.Archivos_TGR"
        ), {"error_extraccion": ERROR_EXTRACCION, "error": "Error"}).one()
        filas = conexion.execute(
            text(f"SELECT {COLUMNAS_PUBLICAS} FROM dbo.Archivos_TGR "
                 "ORDER BY fecha_recepcion DESC, id_archivo DESC "
                 "OFFSET :desplazamiento ROWS FETCH NEXT :limite ROWS ONLY"),
            {"desplazamiento": desplazamiento, "limite": limite},
        ).mappings().all()
        # Deudores de cada informe que esperan revisión manual (casos dudosos y filas rechazadas).
        por_revisar = pendientes_por_informe(conexion, [f["id_archivo"] for f in filas])
    return {"total": total, "con_error": con_error, "limite": limite, "desplazamiento": desplazamiento,
            "archivos": [dict(f) | {"por_revisar": por_revisar.get(f["id_archivo"], 0)} for f in filas]}


@router.get("/archivos/{id_archivo}")
def obtener_archivo(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    with transaccion(conexion):
        fila = conexion.execute(
            text(f"SELECT {COLUMNAS_PUBLICAS} FROM dbo.Archivos_TGR WHERE id_archivo = :id"), {"id": id_archivo}
        ).mappings().one_or_none()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    return dict(fila)


@router.get("/archivos/{id_archivo}/historial")
def historial_archivo(id_archivo: int, conexion: Connection = Depends(obtener_conexion)):
    """Lo que pasó con el documento según la bitácora (RF10): recepción, extracción, ETL, en orden."""
    with transaccion(conexion):
        if conexion.execute(text("SELECT 1 FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                            {"id": id_archivo}).scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
        # JSON_VALUE compara el id exacto (un LIKE confundiría el 17 con el 178).
        filas = conexion.execute(text(
            "SELECT b.id_bitacora, b.accion_ejecutada AS accion, b.timestamp_accion AS fecha, "
            "u.nombre_completo AS usuario, b.detalle_cambio "
            "FROM dbo.Bitacora_Trazabilidad b JOIN dbo.Usuarios u ON u.id_usuario = b.id_usuario "
            "WHERE ISJSON(b.detalle_cambio) = 1 AND JSON_VALUE(b.detalle_cambio, '$.id_archivo') = :id "
            "ORDER BY b.id_bitacora"
        ), {"id": str(id_archivo)}).mappings().all()
    return [{"id_bitacora": f["id_bitacora"], "accion": f["accion"], "fecha": f["fecha"], "usuario": f["usuario"],
             "detalle": json.loads(f["detalle_cambio"])} for f in filas]


@router.get("/archivos/{id_archivo}/documento")
def documento_archivo(
    id_archivo: int,
    conexion: Connection = Depends(obtener_conexion),
    almacen: Path = Depends(obtener_almacen),
):
    """El archivo tal como llegó. PDF e imágenes se abren en el navegador; el resto se descarga."""
    with transaccion(conexion):
        fila = conexion.execute(
            text("SELECT nombre_archivo, ruta_original FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
            {"id": id_archivo},
        ).one_or_none()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    ruta = ruta_segura(almacen, DocumentoOriginal(id_archivo, fila.nombre_archivo, fila.ruta_original))
    if ruta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"{fila.nombre_archivo} está registrado pero no se encuentra en el almacén.")
    extension = ruta.suffix.lower()
    return FileResponse(ruta, media_type=TIPOS_MIME.get(extension, "application/octet-stream"),
                        filename=fila.nombre_archivo,
                        content_disposition_type="inline" if extension in VISIBLES_EN_NAVEGADOR else "attachment")


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
                   "recibidos_hoy": hoy.get(CORREO, 0),
                   "remitentes_autorizados": len(correos_autorizados(conexion))},
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
    autorizados = correos_autorizados(conexion)
    if not autorizados:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="No hay remitentes autorizados: agréguelos en «Remitentes autorizados».")
    try:
        with abrir_buzon() as buzon:
            resumen = revisar_buzon(conexion, buzon, remitentes_autorizados=autorizados,
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


# --- Remitentes autorizados de la casilla (CU02 2a) ---
class NuevoRemitente(BaseModel):
    correo: str = Field(..., max_length=LARGO_MAXIMO_CORREO + 100)  # admite "Nombre <correo>"
    nombre: str | None = Field(None, max_length=LARGO_MAXIMO_NOMBRE)


@router.get("/remitentes")
def listar_remitentes_autorizados(conexion: Connection = Depends(obtener_conexion)):
    return [asdict(remitente) for remitente in listar_remitentes(conexion)]


@router.post("/remitentes", status_code=status.HTTP_201_CREATED)
def agregar_remitente_autorizado(
    datos: NuevoRemitente,
    respuesta: Response,
    conexion: Connection = Depends(obtener_conexion),
):
    """Agrega un remitente (201). Si ya estaba autorizado responde 200 con el existente."""
    try:
        remitente, nuevo = agregar_remitente(conexion, datos.correo, datos.nombre)
    except RemitenteInvalido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not nuevo:
        respuesta.status_code = status.HTTP_200_OK
    return asdict(remitente)


@router.delete("/remitentes/{id_remitente}", status_code=status.HTTP_204_NO_CONTENT)
def quitar_remitente_autorizado(id_remitente: int, conexion: Connection = Depends(obtener_conexion)):
    """Quita (desactiva) un remitente; los correos que envíe desde ahora se ignoran."""
    if not quitar_remitente(conexion, id_remitente):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remitente no encontrado")
