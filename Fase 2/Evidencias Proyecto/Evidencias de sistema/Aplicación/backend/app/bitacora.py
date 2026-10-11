"""Registro de acciones en la Bitácora de Trazabilidad (RF10). La tabla es inalterable: solo se insertan filas."""
import json

from sqlalchemy import Connection, text

USUARIO_SISTEMA = "sistema.ttdh"  # usuario técnico de los procesos automáticos (03_datos_iniciales.sql)


def id_usuario_sistema(conexion: Connection) -> int:
    id_usuario = conexion.execute(
        text("SELECT id_usuario FROM dbo.Usuarios WHERE usuario_ad = :usuario AND activo = 1"),
        {"usuario": USUARIO_SISTEMA},
    ).scalar_one_or_none()
    if id_usuario is None:
        raise RuntimeError(f"No existe el usuario técnico {USUARIO_SISTEMA!r}: ejecute 03_datos_iniciales.sql.")
    return id_usuario


def registrar(conexion: Connection, accion: str, detalle: dict, id_usuario: int | None = None) -> None:
    """Agrega una acción a la bitácora. Sin `id_usuario`, se atribuye al usuario técnico del sistema."""
    conexion.execute(
        text("INSERT INTO dbo.Bitacora_Trazabilidad (id_usuario, accion_ejecutada, detalle_cambio) "
             "VALUES (:id_usuario, :accion, :detalle)"),
        {
            "id_usuario": id_usuario if id_usuario is not None else id_usuario_sistema(conexion),
            "accion": accion,
            "detalle": json.dumps(detalle, ensure_ascii=False, default=str),
        },
    )
