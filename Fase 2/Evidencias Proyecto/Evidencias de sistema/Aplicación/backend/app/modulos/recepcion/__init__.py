"""Recepción de documentos TGR desde la casilla de correo institucional, SFTP y carga web.

Requerimientos: RF01, RN02 (documentos duplicados) — Caso de uso: CU02
Responsable: Héctor Sanhueza

Todos los canales usan `recibir_documento`, que valida el tipo y el tamaño, rechaza documentos ya recibidos
(misma huella SHA-256), guarda el original en el almacén y lo registra en Archivos_TGR con estado 'Recibido'
(Excel, CSV, TXT) o 'Pendiente de Extracción' (PDF e imágenes, que luego normaliza `procesar_pendientes`).

Uso:
    with engine.connect() as conexion:
        resultado = recibir_documento(conexion, contenido, "nomina.xlsx", WEB,
                                      almacen=settings.almacen_documentos, tamano_maximo=20 * 1024 * 1024)
        resultado.aceptado, resultado.motivo, resultado.documento.id_archivo
        revisar_directorio(conexion, settings.sftp_directorio, almacen=..., tamano_maximo=...)
        procesar_pendientes(conexion, settings.almacen_documentos)

Revisión programada de los canales: backend/scripts/revisar_canales.py
"""
from .correo import BuzonImap, conectar_imap, revisar_buzon
from .pendientes import procesar_pendientes, ruta_plantilla
from .registro import (
    CORREO, SFTP, WEB, DatosCorreo, DocumentoRegistrado, MotivoRechazo, ResultadoRecepcion, ResumenCanal,
    recibir_documento,
)
from .sftp import revisar_directorio

__all__ = [
    "CORREO", "SFTP", "WEB", "BuzonImap", "DatosCorreo", "DocumentoRegistrado", "MotivoRechazo",
    "ResultadoRecepcion", "ResumenCanal", "conectar_imap", "procesar_pendientes", "recibir_documento",
    "revisar_buzon", "revisar_directorio", "ruta_plantilla",
]
