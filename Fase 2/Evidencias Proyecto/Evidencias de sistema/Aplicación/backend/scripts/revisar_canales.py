"""Revisa los canales de recepción y normaliza los documentos pendientes (RF01, CU02 "según la programación").

Pensado para ejecutarse periódicamente (Programador de tareas de Windows o cron). Uso, desde backend/:
    python -m scripts.revisar_canales                        # correo, SFTP y extracción
    python -m scripts.revisar_canales --canales sftp         # solo un canal
    python -m scripts.revisar_canales --simular              # muestra lo que haría, sin registrar nada

Rechazar un documento (tipo no permitido, duplicado, etc.) es un resultado normal y queda en la bitácora;
el código de salida es 1 solo si algo falló y quedó pendiente para la próxima ejecución.
No corren dos ejecuciones a la vez: la segunda termina de inmediato mientras exista el archivo de bloqueo.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from app.config import settings
from app.db import engine
from app.modulos.recepcion import conectar_imap, procesar_pendientes, revisar_buzon, revisar_directorio
from app.modulos.recepcion.pendientes import documentos_pendientes
from app.modulos.recepcion.remitentes import correos_autorizados
from app.modulos.recepcion.sftp import archivos_listos

CANALES = ("correo", "sftp", "extraccion")
BLOQUEO = settings.almacen_documentos.parent / ".revisar_canales.lock"
BLOQUEO_VENCIDO = 2 * 60 * 60  # segundos: un bloqueo más antiguo es de una ejecución que terminó mal


class EjecucionEnCurso(Exception):
    pass


@contextmanager
def bloqueo_exclusivo(ruta: Path):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists() and time.time() - ruta.stat().st_mtime > BLOQUEO_VENCIDO:
        print(f"Aviso: se elimina un bloqueo vencido ({ruta})")
        ruta.unlink(missing_ok=True)
    try:
        descriptor = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise EjecucionEnCurso(f"Ya hay una revisión en curso ({ruta})") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield
    finally:
        ruta.unlink(missing_ok=True)


def simular(canales: list[str], antiguedad_minima: float, limite: int) -> None:
    if "correo" in canales:
        if not settings.imap_servidor:
            print("Correo: IMAP_SERVIDOR no configurado, se omite")
        else:
            with conectar_imap(settings.imap_servidor, settings.imap_puerto, settings.imap_usuario,
                               settings.imap_password, settings.imap_carpeta) as buzon:
                print(f"Correo: {len(buzon.no_leidos())} correos no leídos en {settings.imap_carpeta}")
    if "sftp" in canales:
        directorio = settings.sftp_directorio
        listos = archivos_listos(directorio, antiguedad_minima) if directorio.is_dir() else []
        print(f"SFTP: {len(listos)} archivos listos en {directorio}")
        for ruta in listos:
            print(f"  {ruta.name}")
    if "extraccion" in canales:
        with engine.connect() as conexion:
            pendientes = documentos_pendientes(conexion, limite)
        print(f"Extracción: {len(pendientes)} documentos pendientes (máximo {limite})")
        for documento in pendientes:
            print(f"  N° {documento.id_archivo} {documento.nombre_archivo} ({documento.tipo_documento})")


def revisar(canales: list[str], antiguedad_minima: float, limite: int) -> int:
    """Revisa cada canal por separado: si uno falla (p. ej., el servidor de correo no responde), sigue con el resto."""
    maximo = settings.tamano_maximo_mb * 1024 * 1024
    fallas = 0
    with engine.connect() as conexion:
        if "correo" in canales:
            if not settings.imap_servidor:
                print("Correo: IMAP_SERVIDOR no configurado, se omite")
            else:
                try:
                    with conectar_imap(settings.imap_servidor, settings.imap_puerto, settings.imap_usuario,
                                       settings.imap_password, settings.imap_carpeta) as buzon:
                        resumen = revisar_buzon(conexion, buzon, almacen=settings.almacen_documentos,
                                                remitentes_autorizados=correos_autorizados(conexion),
                                                tamano_maximo=maximo)
                    fallas += resumen.fallidos
                    imprimir("Correo", resumen)
                except Exception as exc:  # noqa: BLE001 - se informa y se sigue con los demás canales
                    fallas += 1
                    print(f"Correo: no se pudo revisar ({exc.__class__.__name__}: {exc})")
        if "sftp" in canales:
            try:
                settings.sftp_directorio.mkdir(parents=True, exist_ok=True)
                resumen = revisar_directorio(conexion, settings.sftp_directorio, almacen=settings.almacen_documentos,
                                             tamano_maximo=maximo, antiguedad_minima=antiguedad_minima)
                fallas += resumen.fallidos
                imprimir("SFTP", resumen)
            except Exception as exc:  # noqa: BLE001
                fallas += 1
                print(f"SFTP: no se pudo revisar ({exc.__class__.__name__}: {exc})")
        if "extraccion" in canales:
            try:
                extraccion = procesar_pendientes(conexion, settings.almacen_documentos, limite)
                print(f"Extracción: {extraccion.normalizados} normalizados, {extraccion.con_error} con error "
                      f"de extracción, {extraccion.omitidos} omitidos")
            except Exception as exc:  # noqa: BLE001
                fallas += 1
                print(f"Extracción: no se pudo completar ({exc.__class__.__name__}: {exc})")
    return fallas


def imprimir(canal: str, resumen) -> None:
    print(f"{canal}: {resumen.registrados} registrados, {resumen.rechazados} rechazados, "
          f"{resumen.fallidos} fallidos, {resumen.omitidos} omitidos")
    for error in resumen.errores:
        print(f"  {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revisa los canales de recepción de TTDH Automation.")
    parser.add_argument("--canales", nargs="+", choices=CANALES, default=list(CANALES),
                        help="canales a revisar (por defecto todos)")
    parser.add_argument("--simular", action="store_true", help="muestra lo que haría, sin registrar nada")
    parser.add_argument("--limite-extraccion", type=int, default=10,
                        help="máximo de documentos a normalizar por ejecución (por defecto 10)")
    parser.add_argument("--antiguedad-minima", type=float, default=60,
                        help="segundos sin cambios antes de leer un archivo SFTP (por defecto 60)")
    args = parser.parse_args(argv)
    if args.limite_extraccion < 1:
        parser.error("--limite-extraccion debe ser 1 o mayor")

    print(f"Base de datos: {settings.db_server}/{settings.db_name} | almacén: {settings.almacen_documentos}")
    if args.simular:
        simular(args.canales, args.antiguedad_minima, args.limite_extraccion)
        return 0
    try:
        with bloqueo_exclusivo(BLOQUEO):
            fallas = revisar(args.canales, args.antiguedad_minima, args.limite_extraccion)
    except EjecucionEnCurso as exc:
        print(exc)
        return 0  # no es un error: la ejecución anterior sigue trabajando
    if fallas:
        print(f"Terminó con {fallas} elementos fallidos: quedan para la próxima revisión.")
        return 1
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
