"""Ejecución del ETL de casos TGR: CSV -> stg.casos_tgr -> core.casos_tgr (RF02, RF05, RF10).

Equivale a correr `transformacion_carga.ktr` y luego `Normalizar_TGR.ktr`, con dos diferencias:
- Solo se normalizan las filas de este archivo (el .ktr relee todo stg.casos_tgr en cada ejecución).
- Los duplicados se buscan en el lote y también en core.casos_tgr, así cargar dos veces el mismo
  archivo no duplica casos. Cada fila queda en etl.resultados con su resultado y motivo (06_etl.sql).

Todo ocurre en una transacción: si algo falla, no queda nada a medias.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

from ... import bitacora
from ...db import transaccion
from .reglas import COLUMNAS_CSV, COLUMNAS_STG, Caso, Rechazo, normalizar

CARGADO, RECHAZADO, DUPLICADO = "Cargado", "Rechazado", "Duplicado"  # etl.resultados.resultado
PROCESADO, ERROR = "Procesado", "Error"  # estado_archivo de Archivos_TGR después del ETL
_LOTE_CONSULTA = 1000  # SQL Server admite hasta 2100 parámetros por consulta


class ErrorFormatoCsv(ValueError):
    """El archivo no tiene la estructura que espera el ETL: no se carga ninguna fila."""


class ArchivoNoProcesable(Exception):
    """El documento no existe, no es un CSV TGR o ya pasó por el ETL."""

    def __init__(self, mensaje: str, *, no_encontrado: bool = False):
        super().__init__(mensaje)
        self.no_encontrado = no_encontrado


@dataclass(frozen=True)
class ResumenEtl:
    id_ejecucion: int
    filas_leidas: int
    cargadas: int
    rechazadas: int
    duplicadas: int


def leer_csv(ruta: Path) -> list[dict[str, str]]:
    """Lee el CSV TGR (UTF-8 con o sin BOM, separado por ';') como filas con los nombres de stg."""
    try:
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            filas = list(csv.reader(archivo, delimiter=";", quotechar='"'))
    except UnicodeDecodeError as error:
        raise ErrorFormatoCsv("El archivo no está en UTF-8.") from error
    if not filas:
        raise ErrorFormatoCsv("El archivo está vacío.")
    encabezado, *datos = filas
    if len(encabezado) != len(COLUMNAS_CSV):
        raise ErrorFormatoCsv(
            f"Se esperaban {len(COLUMNAS_CSV)} columnas separadas por ';' y el encabezado tiene {len(encabezado)}."
        )
    resultado = []
    for numero, fila in enumerate(datos, start=2):
        if not any(valor.strip() for valor in fila):
            continue  # línea en blanco
        if len(fila) != len(COLUMNAS_CSV):
            raise ErrorFormatoCsv(f"La fila {numero} tiene {len(fila)} columnas y deben ser {len(COLUMNAS_CSV)}.")
        resultado.append(dict(zip(COLUMNAS_STG, fila)))
    return resultado


def es_csv_tgr(ruta: Path) -> bool:
    """True si el encabezado es el del CSV TGR (21 columnas separadas por ';', partiendo por NOMBRE DOCUMENTO).

    Los CSV con otro formato (por ejemplo, las nóminas simuladas) no pasan por este ETL.
    """
    try:
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            encabezado = next(csv.reader(archivo, delimiter=";", quotechar='"'), [])
    except (OSError, UnicodeDecodeError):
        return False
    return len(encabezado) == len(COLUMNAS_CSV) and encabezado[0].strip().upper() == COLUMNAS_CSV[0]


def _cargar_staging(conexion: Connection, filas: list[dict[str, str]], archivo_origen: str) -> list[int]:
    """transformacion_carga.ktr: guarda las filas tal como llegaron. Devuelve el id_stg de cada una."""
    columnas = ", ".join(COLUMNAS_STG)
    valores = ", ".join(f":{columna}" for columna in COLUMNAS_STG)
    consulta = text(
        f"INSERT INTO stg.casos_tgr ({columnas}, archivo_origen) OUTPUT INSERTED.id_stg "
        f"VALUES ({valores}, :archivo_origen)"
    )
    ids = []
    for numero, fila in enumerate(filas, start=2):
        try:
            ids.append(conexion.execute(consulta, {**fila, "archivo_origen": archivo_origen}).scalar_one())
        except DBAPIError as error:
            raise ErrorFormatoCsv(f"La fila {numero} tiene un valor más largo que lo permitido.") from error
    return ids


def casos_existentes(conexion: Connection, casos: list[Caso]) -> dict[tuple, int]:
    """id_caso de los casos que ya están en core.casos_tgr, por su llave de duplicado."""
    ruts = sorted({caso.columnas["rut_limpio"] for caso in casos})
    existentes = {}
    for inicio in range(0, len(ruts), _LOTE_CONSULTA):
        parte = ruts[inicio:inicio + _LOTE_CONSULTA]
        marcadores = ", ".join(f":r{i}" for i in range(len(parte)))
        filas = conexion.execute(
            text(f"SELECT id_caso, rut_limpio, dv_limpio, rol, fec_ing FROM core.casos_tgr "
                 f"WHERE rut_limpio IN ({marcadores})"),
            {f"r{i}": rut for i, rut in enumerate(parte)},
        )
        for id_caso, rut, dv, rol, fec_ing in filas:
            existentes.setdefault((rut, dv, rol, fec_ing), id_caso)
    return existentes


def insertar_caso(conexion: Connection, caso: Caso) -> int:
    columnas = ", ".join(caso.columnas)
    valores = ", ".join(f":{columna}" for columna in caso.columnas)
    return conexion.execute(
        text(f"INSERT INTO core.casos_tgr ({columnas}) OUTPUT INSERTED.id_caso VALUES ({valores})"),
        caso.columnas,
    ).scalar_one()


def ejecutar(conexion: Connection, ruta: Path, id_archivo: int | None = None, nombre: str | None = None) -> ResumenEtl:
    """Carga y normaliza un CSV TGR. `nombre`: el original del documento (por defecto, el del archivo en disco).

    Lanza ErrorFormatoCsv si el archivo no tiene la estructura esperada.
    """
    return ejecutar_filas(conexion, leer_csv(ruta), nombre or ruta.name, id_archivo)


def ejecutar_filas(conexion: Connection, filas: list[dict[str, str]], nombre: str,
                   id_archivo: int | None = None) -> ResumenEtl:
    """Carga y normaliza filas con las columnas de stg.casos_tgr (de un CSV o de un informe extraído)."""
    with transaccion(conexion):
        id_ejecucion = conexion.execute(
            text("INSERT INTO etl.ejecuciones (id_archivo, archivo_origen, filas_leidas) "
                 "OUTPUT INSERTED.id_ejecucion VALUES (:id_archivo, :archivo_origen, :filas)"),
            {"id_archivo": id_archivo, "archivo_origen": nombre, "filas": len(filas)},
        ).scalar_one()
        ids_stg = _cargar_staging(conexion, filas, nombre)

        normalizadas = [normalizar(fila) for fila in filas]
        vistos = casos_existentes(conexion, [n for n in normalizadas if isinstance(n, Caso)])
        resultados = []  # (id_stg, resultado, motivo, id_caso)
        for id_stg, normalizada in zip(ids_stg, normalizadas):
            if isinstance(normalizada, Rechazo):
                resultados.append((id_stg, RECHAZADO, normalizada.motivo, None))
            elif normalizada.llave in vistos:
                id_caso = vistos[normalizada.llave]
                resultados.append((id_stg, DUPLICADO, f"Mismo RUT, rol y fecha de ingreso que el caso #{id_caso}",
                                   id_caso))
            else:
                id_caso = insertar_caso(conexion, normalizada)
                vistos[normalizada.llave] = id_caso
                resultados.append((id_stg, CARGADO, None, id_caso))

        if resultados:
            conexion.execute(
                text("INSERT INTO etl.resultados (id_ejecucion, id_stg, resultado, motivo, id_caso) "
                     "VALUES (:id_ejecucion, :id_stg, :resultado, :motivo, :id_caso)"),
                [{"id_ejecucion": id_ejecucion, "id_stg": id_stg, "resultado": resultado,
                  "motivo": motivo, "id_caso": id_caso} for id_stg, resultado, motivo, id_caso in resultados],
            )
        conteo = {r: sum(1 for _, resultado, _, _ in resultados if resultado == r)
                  for r in (CARGADO, RECHAZADO, DUPLICADO)}
        conexion.execute(
            text("UPDATE etl.ejecuciones SET cargadas = :c, rechazadas = :r, duplicadas = :d "
                 "WHERE id_ejecucion = :id"),
            {"c": conteo[CARGADO], "r": conteo[RECHAZADO], "d": conteo[DUPLICADO], "id": id_ejecucion},
        )
        resumen = ResumenEtl(id_ejecucion, len(filas), conteo[CARGADO], conteo[RECHAZADO], conteo[DUPLICADO])
        bitacora.registrar(conexion, "Ejecución ETL", {
            "id_ejecucion": id_ejecucion, "archivo": nombre, "id_archivo": id_archivo,
            "filas_leidas": resumen.filas_leidas, "cargadas": resumen.cargadas,
            "rechazadas": resumen.rechazadas, "duplicadas": resumen.duplicadas,
        })
    return resumen


def procesar_archivo(conexion: Connection, id_archivo: int, almacen: Path) -> ResumenEtl:
    """Pasa por el ETL un documento ya recibido (Archivos_TGR) y actualiza su estado.

    Queda "Procesado", con total_registros = filas leídas. Si el CSV no tiene la estructura esperada,
    queda "Error" con el motivo en la bitácora, y se relanza ErrorFormatoCsv.
    """
    with transaccion(conexion):
        documento = conexion.execute(
            text("SELECT nombre_archivo, tipo_documento, ruta_original, estado_archivo "
                 "FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
            {"id": id_archivo},
        ).mappings().one_or_none()
        if documento is None:
            raise ArchivoNoProcesable("Archivo no encontrado", no_encontrado=True)
        if documento["tipo_documento"] != "CSV":
            raise ArchivoNoProcesable("Solo los CSV pasan por el ETL de casos TGR.")
        anterior = conexion.execute(
            text("SELECT TOP 1 id_ejecucion FROM etl.ejecuciones WHERE id_archivo = :id"), {"id": id_archivo}
        ).scalar_one_or_none()
        if anterior is not None:
            raise ArchivoNoProcesable(f"El archivo ya se procesó (ejecución #{anterior}).")

    ruta = almacen / documento["ruta_original"]
    if not es_csv_tgr(ruta):
        raise ArchivoNoProcesable("El CSV no tiene el encabezado TGR (21 columnas, desde NOMBRE DOCUMENTO).")
    try:
        # Transacción externa: la carga y el cambio de estado se confirman juntos.
        with transaccion(conexion):
            resumen = ejecutar(conexion, ruta, id_archivo, documento["nombre_archivo"])
            _cambiar_estado(conexion, id_archivo, PROCESADO, resumen.filas_leidas)
    except ErrorFormatoCsv as error:
        with transaccion(conexion):
            _cambiar_estado(conexion, id_archivo, ERROR, None)
            bitacora.registrar(conexion, "Ejecución ETL rechazada",
                               {"id_archivo": id_archivo, "archivo": documento["nombre_archivo"], "motivo": str(error)})
        raise
    return resumen


def _cambiar_estado(conexion: Connection, id_archivo: int, estado: str, total_registros: int | None) -> None:
    conexion.execute(
        text("UPDATE dbo.Archivos_TGR SET estado_archivo = :estado, total_registros = :total WHERE id_archivo = :id"),
        {"estado": estado, "total": total_registros, "id": id_archivo},
    )
