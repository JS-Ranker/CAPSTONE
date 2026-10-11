"""Canal de correo (CU02 pasos 1, 2 y 7): lee la casilla institucional y registra los adjuntos.

Se procesan los correos no leídos. Cada correo se marca como leído recién después de confirmar su registro;
si algo falla queda sin leer y se reintenta en la próxima revisión (los adjuntos ya registrados se detectan
como duplicados por su huella, así que reintentar es seguro).

Limitación: el remitente se toma del encabezado From, que puede falsificarse; verificar SPF/DKIM le
corresponde al servidor de correo institucional.
"""
import email
import imaplib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import default as politica_por_defecto
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import Connection

from ... import bitacora
from ...db import transaccion
from .registro import CORREO, DatosCorreo, ResumenCanal, recibir_documento, resumen_para_bitacora

TIEMPO_ESPERA_IMAP = 30  # segundos
REVISION_CORREO = "Revisión de casilla de correo"  # acción de bitácora
# Imágenes insertadas en el cuerpo más pequeñas que esto se consideran logos de firma, no nóminas.
TAMANO_MINIMO_IMAGEN_EN_LINEA = 20 * 1024  # bytes


@dataclass(frozen=True)
class CorreoRecibido:
    uid: str
    contenido: bytes  # mensaje completo (RFC 822)


class Buzon(Protocol):
    def no_leidos(self) -> list[CorreoRecibido]: ...
    def marcar_procesado(self, uid: str) -> None: ...


class BuzonImap:
    """Casilla IMAP con SSL. Lee sin marcar como leído (BODY.PEEK) hasta que el correo se procesa."""

    def __init__(self, cliente: imaplib.IMAP4, carpeta: str):
        self._cliente = cliente
        estado, _ = cliente.select(carpeta)
        if estado != "OK":
            raise RuntimeError(f"No se pudo abrir la carpeta {carpeta!r} de la casilla")

    def no_leidos(self) -> list[CorreoRecibido]:
        estado, datos = self._cliente.uid("SEARCH", None, "UNSEEN")
        if estado != "OK":
            raise RuntimeError("La casilla rechazó la búsqueda de correos no leídos")
        correos = []
        for uid in datos[0].split():
            estado, partes = self._cliente.uid("FETCH", uid, "(BODY.PEEK[])")
            if estado == "OK" and partes and isinstance(partes[0], tuple):
                correos.append(CorreoRecibido(uid.decode(), partes[0][1]))
        return correos

    def marcar_procesado(self, uid: str) -> None:
        self._cliente.uid("STORE", uid, "+FLAGS", "(\\Seen)")


@contextmanager
def conectar_imap(servidor: str, puerto: int, usuario: str, password: str, carpeta: str) -> Iterator[BuzonImap]:
    cliente = imaplib.IMAP4_SSL(servidor, puerto, timeout=TIEMPO_ESPERA_IMAP)
    try:
        cliente.login(usuario, password)
        yield BuzonImap(cliente, carpeta)
    finally:
        try:
            cliente.logout()
        except (imaplib.IMAP4.error, OSError):
            pass  # la sesión ya estaba cerrada; no hay nada más que liberar


def revisar_buzon(
    conexion: Connection,
    buzon: Buzon,
    *,
    remitentes_autorizados: tuple[str, ...],
    almacen: Path,
    tamano_maximo: int,
) -> ResumenCanal:
    """Registra los adjuntos de los correos no leídos de remitentes autorizados."""
    if not remitentes_autorizados:
        raise ValueError("No hay remitentes autorizados: agréguelos en la pantalla de ingesta")
    autorizados = {remitente.lower() for remitente in remitentes_autorizados}
    resumen = ResumenCanal()

    for recibido in buzon.no_leidos():
        try:
            with transaccion(conexion):
                _procesar_correo(conexion, recibido, autorizados, almacen, tamano_maximo, resumen)
        except Exception as exc:  # noqa: BLE001 - el correo queda sin leer y se reintenta en la próxima revisión
            resumen.fallidos += 1
            resumen.errores.append(f"Correo {recibido.uid}: {exc.__class__.__name__}")
            continue
        buzon.marcar_procesado(recibido.uid)

    with transaccion(conexion):  # deja constancia de la revisión (la pantalla de ingesta muestra la última)
        bitacora.registrar(conexion, REVISION_CORREO, resumen_para_bitacora(resumen))
    return resumen


def _procesar_correo(conexion, recibido: CorreoRecibido, autorizados: set[str], almacen: Path,
                     tamano_maximo: int, resumen: ResumenCanal) -> None:
    mensaje: EmailMessage = email.message_from_bytes(recibido.contenido, policy=politica_por_defecto)
    remitente = parseaddr(str(mensaje.get("From", "")))[1].lower()
    datos = DatosCorreo(remitente=remitente, asunto=str(mensaje.get("Subject", "")) or None,
                        fecha=_fecha_local(mensaje.get("Date")))
    contexto = {"remitente": remitente, "asunto": datos.asunto, "fecha_correo": datos.fecha}

    if remitente not in autorizados:  # CU02 2a
        bitacora.registrar(conexion, "Correo ignorado: remitente no autorizado", contexto)
        resumen.omitidos += 1
        return

    adjuntos = documentos_del_correo(mensaje)
    if not adjuntos:  # CU02 2b (la notificación al analista queda pendiente: aún no hay módulo de avisos)
        bitacora.registrar(conexion, "Correo sin adjuntos", contexto)
        resumen.omitidos += 1
        return

    for adjunto in adjuntos:
        resultado = recibir_documento(conexion, adjunto.get_payload(decode=True) or b"", adjunto.get_filename(),
                                      CORREO, almacen=almacen, tamano_maximo=tamano_maximo, correo=datos)
        if resultado.aceptado:
            resumen.registrados += 1
        else:
            resumen.rechazados += 1
            resumen.errores.append(f"{adjunto.get_filename()}: {resultado.motivo.value}. {resultado.detalle}".strip())


def documentos_del_correo(mensaje: EmailMessage) -> list[EmailMessage]:
    """Archivos del correo, en cualquier nivel del mensaje.

    No basta con los adjuntos del primer nivel: Gmail deja dentro del cuerpo (multipart/related, "inline")
    las fotos que se arrastran al texto, y otros clientes hacen lo mismo con PDF. Se omiten solo las imágenes
    del cuerpo más pequeñas que TAMANO_MINIMO_IMAGEN_EN_LINEA, que suelen ser logos de la firma.
    """
    documentos = []
    for parte in mensaje.walk():
        if parte.is_multipart() or not parte.get_filename():
            continue
        es_imagen_en_linea = parte.get_content_disposition() == "inline" and parte.get_content_maintype() == "image"
        if es_imagen_en_linea and len(parte.get_payload(decode=True) or b"") < TAMANO_MINIMO_IMAGEN_EN_LINEA:
            continue
        documentos.append(parte)
    return documentos


def _fecha_local(valor):
    """Fecha del correo en la hora local del servidor (como fecha_recepcion), sin zona horaria."""
    if not valor:
        return None
    try:
        fecha = parsedate_to_datetime(str(valor))
    except (TypeError, ValueError):
        return None
    return fecha.astimezone().replace(tzinfo=None) if fecha.tzinfo else fecha
