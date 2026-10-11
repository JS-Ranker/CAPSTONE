"""Registro de un documento recibido por cualquier canal (RF01, RN02, CU02 pasos 3 y 4).

Valida el tipo y el tamaño, rechaza documentos ya recibidos (misma huella SHA-256, aunque cambie el nombre
o el canal), guarda el original en el almacén y lo registra en Archivos_TGR. Cada aceptación o rechazo
queda en la bitácora. Los rechazos son resultados esperados, no excepciones: así el rechazo se registra
en la bitácora y la transacción del llamador se confirma igual.
"""
import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from ... import bitacora
from ...db import transaccion
from ..extraccion.pdf_texto import tiene_texto

CORREO, SFTP, WEB = "Correo", "SFTP", "Web"  # canal_origen de Archivos_TGR
RECIBIDO, PENDIENTE_EXTRACCION = "Recibido", "Pendiente de Extracción"  # estado_archivo inicial

# CU02 paso 3: tipos permitidos. Los PDF se clasifican al leerlos (con texto o escaneado).
TIPOS_POR_EXTENSION = {
    ".xlsx": "Excel", ".xls": "Excel", ".csv": "CSV", ".txt": "TXT",
    ".pdf": "PDF", ".jpg": "Imagen", ".jpeg": "Imagen", ".png": "Imagen",
}
NO_ESTRUCTURADOS = {"PDF con texto", "PDF escaneado", "Imagen"}  # pasan por la extracción (CU12)

_CARACTERES_NO_VALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_LARGO_MAXIMO_NOMBRE = 150


class MotivoRechazo(Enum):
    TIPO_NO_PERMITIDO = "Tipo de archivo no permitido"  # CU02 3a
    VACIO = "El archivo está vacío"
    DEMASIADO_GRANDE = "El archivo supera el tamaño máximo"
    DUPLICADO = "El documento ya fue recibido"  # RN02, CU02 4a


@dataclass(frozen=True)
class DatosCorreo:
    remitente: str
    asunto: str | None
    fecha: datetime | None  # hora local del servidor, igual que fecha_recepcion


@dataclass(frozen=True)
class DocumentoRegistrado:
    id_archivo: int
    nombre_archivo: str
    canal_origen: str
    tipo_documento: str
    estado_archivo: str
    ruta_original: str  # relativa al almacén de documentos
    hash_sha256: str


@dataclass(frozen=True)
class ResultadoRecepcion:
    documento: DocumentoRegistrado | None = None
    motivo: MotivoRechazo | None = None
    detalle: str = ""
    id_archivo_existente: int | None = None  # solo en DUPLICADO

    @property
    def aceptado(self) -> bool:
        return self.documento is not None


@dataclass
class ResumenCanal:
    """Conteo de una revisión de canal (correo o SFTP)."""
    registrados: int = 0
    rechazados: int = 0
    fallidos: int = 0  # quedan para la próxima revisión
    omitidos: int = 0  # correos ignorados o sin adjuntos; archivos aún en copia
    errores: list[str] = field(default_factory=list)


def resumen_para_bitacora(resumen: ResumenCanal) -> dict:
    return {"registrados": resumen.registrados, "rechazados": resumen.rechazados, "fallidos": resumen.fallidos,
            "omitidos": resumen.omitidos, "errores": resumen.errores[:20]}


def nombre_seguro(nombre: str) -> str:
    """Nombre de archivo sin rutas ni caracteres no válidos (evita escribir fuera del almacén)."""
    nombre = re.split(r"[\\/]", nombre or "")[-1]
    nombre = _CARACTERES_NO_VALIDOS.sub("_", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip(" .")
    if len(nombre) > _LARGO_MAXIMO_NOMBRE:
        base, extension = os.path.splitext(nombre)
        nombre = base[: _LARGO_MAXIMO_NOMBRE - len(extension)] + extension
    return nombre or "documento"


def tipo_documento(ruta: Path) -> str:
    """Tipo según Archivos_TGR. Un PDF sin texto seleccionable (o ilegible) se trata como escaneado."""
    tipo = TIPOS_POR_EXTENSION[ruta.suffix.lower()]
    if tipo != "PDF":
        return tipo
    try:
        return "PDF con texto" if tiene_texto(ruta) else "PDF escaneado"
    except Exception:  # noqa: BLE001 - PDF dañado: lo detectará la extracción y quedará 'Error de Extracción'
        return "PDF escaneado"


def recibir_documento(
    conexion: Connection,
    contenido: bytes,
    nombre: str,
    canal: str,
    *,
    almacen: Path,
    tamano_maximo: int,
    correo: DatosCorreo | None = None,
    id_usuario: int | None = None,
) -> ResultadoRecepcion:
    """Valida, guarda y registra un documento. `tamano_maximo` en bytes; `correo` solo para el canal Correo."""
    if canal not in (CORREO, SFTP, WEB):
        raise ValueError(f"Canal desconocido: {canal!r}")
    if (canal == CORREO) != (correo is not None):
        raise ValueError("Los datos del correo se informan solo (y siempre) en el canal Correo.")

    nombre = nombre_seguro(nombre)
    extension = Path(nombre).suffix.lower()
    huella = hashlib.sha256(contenido).hexdigest()
    contexto = {"nombre_archivo": nombre, "canal": canal, "bytes": len(contenido), "hash_sha256": huella}
    if correo:
        contexto |= {"remitente": correo.remitente, "asunto": correo.asunto}

    with transaccion(conexion):
        if extension not in TIPOS_POR_EXTENSION:
            permitidos = ", ".join(sorted(TIPOS_POR_EXTENSION))
            return _rechazar(conexion, MotivoRechazo.TIPO_NO_PERMITIDO, f"Se aceptan: {permitidos}.", contexto, id_usuario)
        if not contenido:
            return _rechazar(conexion, MotivoRechazo.VACIO, "", contexto, id_usuario)
        if len(contenido) > tamano_maximo:
            return _rechazar(conexion, MotivoRechazo.DEMASIADO_GRANDE,
                             f"Máximo {tamano_maximo // (1024 * 1024)} MB.", contexto, id_usuario)

        existente = _archivo_con_huella(conexion, huella)
        if existente is not None:
            return _rechazar_duplicado(conexion, existente, contexto, id_usuario)

        ruta_relativa = Path(datetime.now().strftime("%Y/%m")) / f"{huella[:16]}_{nombre}"
        destino = almacen / ruta_relativa
        creado = _guardar(destino, contenido)
        tipo = tipo_documento(destino)
        estado = PENDIENTE_EXTRACCION if tipo in NO_ESTRUCTURADOS else RECIBIDO
        try:
            # Punto de guardado: si otra carga del mismo archivo se registra a la vez, el índice único
            # UX_Archivos_hash rechaza esta y la transacción del llamador sigue siendo válida.
            with conexion.begin_nested():
                id_archivo = _insertar(conexion, nombre, canal, tipo, estado, ruta_relativa, huella, correo)
        except IntegrityError:
            existente = _archivo_con_huella(conexion, huella)
            if existente is None:
                raise
            return _rechazar_duplicado(conexion, existente, contexto, id_usuario)  # el original es el mismo archivo
        except Exception:
            if creado:
                destino.unlink(missing_ok=True)
            raise

        documento = DocumentoRegistrado(id_archivo, nombre, canal, tipo, estado, ruta_relativa.as_posix(), huella)
        bitacora.registrar(conexion, "Recepción de documento",
                           contexto | {"id_archivo": id_archivo, "tipo_documento": tipo, "estado": estado}, id_usuario)
        return ResultadoRecepcion(documento=documento)


def _archivo_con_huella(conexion: Connection, huella: str) -> int | None:
    return conexion.execute(
        text("SELECT id_archivo FROM dbo.Archivos_TGR WHERE hash_sha256 = :huella"), {"huella": huella}
    ).scalar_one_or_none()


def _guardar(destino: Path, contenido: bytes) -> bool:
    """Escribe el original de forma atómica. Devuelve False si ya existía (mismo contenido: la ruta incluye la huella)."""
    if destino.exists():
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{uuid.uuid4().hex}.tmp")
    try:
        temporal.write_bytes(contenido)
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return True


def _insertar(conexion, nombre, canal, tipo, estado, ruta_relativa: Path, huella, correo: DatosCorreo | None) -> int:
    asunto = correo.asunto[:255] if correo and correo.asunto else None
    return conexion.execute(
        text("""
            INSERT INTO dbo.Archivos_TGR
                (nombre_archivo, canal_origen, remitente, asunto_correo, fecha_correo,
                 tipo_documento, ruta_original, estado_archivo, hash_sha256)
            OUTPUT INSERTED.id_archivo
            VALUES (:nombre, :canal, :remitente, :asunto, :fecha_correo, :tipo, :ruta, :estado, :huella)
        """),
        {
            "nombre": nombre, "canal": canal, "tipo": tipo, "estado": estado, "huella": huella,
            "ruta": ruta_relativa.as_posix(),
            "remitente": correo.remitente if correo else None,
            "asunto": asunto,
            "fecha_correo": correo.fecha if correo else None,
        },
    ).scalar_one()


def _rechazar(conexion, motivo: MotivoRechazo, detalle: str, contexto: dict, id_usuario,
              id_archivo_existente: int | None = None) -> ResultadoRecepcion:
    bitacora.registrar(conexion, "Recepción rechazada",
                       contexto | {"motivo": motivo.value, "detalle": detalle, "id_archivo_existente": id_archivo_existente},
                       id_usuario)
    return ResultadoRecepcion(motivo=motivo, detalle=detalle, id_archivo_existente=id_archivo_existente)


def _rechazar_duplicado(conexion, id_existente: int, contexto: dict, id_usuario) -> ResultadoRecepcion:
    return _rechazar(conexion, MotivoRechazo.DUPLICADO,
                     f"Mismo contenido que el archivo N° {id_existente}.", contexto, id_usuario, id_existente)
