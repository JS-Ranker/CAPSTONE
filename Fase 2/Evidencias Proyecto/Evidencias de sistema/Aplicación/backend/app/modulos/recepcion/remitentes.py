"""Remitentes autorizados de la casilla de correo (CU02 paso 2), guardados en Remitentes_Autorizados.

Se administran desde la pantalla de ingesta. Quitar un remitente lo desactiva (no se borra), y volver a
agregarlo lo reactiva. Cada cambio queda en la bitácora.
"""
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LARGO_MAXIMO_CORREO, LARGO_MAXIMO_NOMBRE = 255, 150


class RemitenteInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Remitente:
    id_remitente: int
    correo: str
    nombre: str | None
    fecha_creacion: datetime


def normalizar_correo(correo: str) -> str:
    """Correo en minúsculas y sin espacios; acepta 'Nombre <correo@dominio.cl>'."""
    correo = (correo or "").strip()
    if "<" in correo and correo.endswith(">"):
        correo = correo[correo.rindex("<") + 1:-1].strip()
    correo = correo.lower()
    if not _CORREO.match(correo) or len(correo) > LARGO_MAXIMO_CORREO:
        raise RemitenteInvalido("El correo no tiene un formato válido (ejemplo: nominas@tgr.cl).")
    return correo


def correos_autorizados(conexion: Connection) -> tuple[str, ...]:
    with transaccion(conexion):
        return tuple(conexion.execute(
            text("SELECT correo FROM dbo.Remitentes_Autorizados WHERE activo = 1")
        ).scalars())


def listar_remitentes(conexion: Connection) -> list[Remitente]:
    with transaccion(conexion):
        filas = conexion.execute(text(
            "SELECT id_remitente, correo, nombre, fecha_creacion FROM dbo.Remitentes_Autorizados "
            "WHERE activo = 1 ORDER BY correo"
        )).all()
    return [Remitente(*fila) for fila in filas]


def agregar_remitente(conexion: Connection, correo: str, nombre: str | None = None) -> tuple[Remitente, bool]:
    """Agrega (o reactiva) un remitente. Devuelve el remitente y si es nuevo; False si ya estaba activo."""
    correo = normalizar_correo(correo)
    nombre = (nombre or "").strip()[:LARGO_MAXIMO_NOMBRE] or None
    with transaccion(conexion):
        existente = conexion.execute(
            text("SELECT id_remitente, activo FROM dbo.Remitentes_Autorizados WITH (UPDLOCK, HOLDLOCK) "
                 "WHERE correo = :correo"),
            {"correo": correo},
        ).one_or_none()
        if existente and existente.activo:
            return _buscar(conexion, existente.id_remitente), False
        if existente:
            conexion.execute(
                text("UPDATE dbo.Remitentes_Autorizados SET activo = 1, nombre = COALESCE(:nombre, nombre) "
                     "WHERE id_remitente = :id"),
                {"nombre": nombre, "id": existente.id_remitente},
            )
            id_remitente = existente.id_remitente
        else:
            id_remitente = conexion.execute(
                text("INSERT INTO dbo.Remitentes_Autorizados (correo, nombre) OUTPUT INSERTED.id_remitente "
                     "VALUES (:correo, :nombre)"),
                {"correo": correo, "nombre": nombre},
            ).scalar_one()
        bitacora.registrar(conexion, "Remitente autorizado agregado", {"correo": correo, "nombre": nombre})
        return _buscar(conexion, id_remitente), True


def quitar_remitente(conexion: Connection, id_remitente: int) -> bool:
    """Desactiva un remitente. Devuelve False si no existía o ya estaba inactivo."""
    with transaccion(conexion):
        correo = conexion.execute(
            text("UPDATE dbo.Remitentes_Autorizados SET activo = 0 OUTPUT INSERTED.correo "
                 "WHERE id_remitente = :id AND activo = 1"),
            {"id": id_remitente},
        ).scalar_one_or_none()
        if correo is None:
            return False
        bitacora.registrar(conexion, "Remitente autorizado quitado", {"correo": correo})
        return True


def _buscar(conexion: Connection, id_remitente: int) -> Remitente:
    fila = conexion.execute(
        text("SELECT id_remitente, correo, nombre, fecha_creacion FROM dbo.Remitentes_Autorizados "
             "WHERE id_remitente = :id"),
        {"id": id_remitente},
    ).one()
    return Remitente(*fila)
