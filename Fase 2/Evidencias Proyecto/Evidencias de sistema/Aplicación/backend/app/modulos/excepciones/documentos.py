"""Revisión manual de informes con 'Error de Extracción' (CU05, CU12 5b, RN05).

Un informe cuyo detalle no cuadra con sus totales (o que no se pudo leer) no llega al ETL. La extracción guarda
lo que alcanzó a leer (etl.extracciones y etl.extraccion_filas) y aquí el analista lo corrige en una grilla, junto
al documento original, y lo envía al ETL; o lo descarta; o lo deja pendiente / pide volver a extraerlo.

La corrección vuelve a pasar por la verificación de totales del documento: no se carga un informe que no cuadre.
Los campos que el analista toca se consideran verificados (confianza 100); los que no, conservan la confianza del
OCR y, si es baja, el caso se carga marcado para revisión (RN05). Cada acción agrega una fila a
etl.revisiones_documento (historial) y a la bitácora.
"""
import json
import re
from dataclasses import dataclass

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion
from ..extraccion.persistencia import ExtraccionGuardada, cargar_extraccion
from ..extraccion.plantilla import (
    CAMPOS_CRITICOS, COLUMNAS_PLANTILLA, ERROR_EXTRACCION, NORMALIZADO, UMBRAL_CONFIANZA, RegistroExtraido,
    ResultadoExtraccion, escribir_plantilla,
)
from ..cruce.servicio import cruzar_sin_fallar
from ..ia.servicio import analizar_sin_fallar
from ..recepcion.documentos import DocumentoOriginal
from ..recepcion.pendientes import DocumentoPendiente, cargar_en_etl, ruta_plantilla
from ..recepcion.registro import PENDIENTE_EXTRACCION
from .servicio import (
    DESCARTADO, DOCUMENTO, PENDIENTE, RESUELTO, AccionNoPermitida, DatosInvalidos, ExcepcionNoEncontrada,
    _observacion, _resumen,
)

DESCARTAR, DEJAR_PENDIENTE, VOLVER_A_EXTRAER = "descartar", "pendiente", "reextraer"
MAXIMO_FILAS = 500
ETIQUETAS = {
    "rut": "RUT", "nombre": "Nombre", "id_demanda": "ID demanda", "n_resolucion": "N° resolución",
    "monto_solicitado": "Monto solicitado", "tipo_embargo": "Tipo de embargo", "expediente": "Expediente",
    "tesoreria": "Tesorería", "fecha_oficio": "Fecha del oficio",
}
_DIA_MES_ANIO = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")


@dataclass(frozen=True)
class FilaCorregida:
    orden: int | None  # posición en lo extraído; None si el analista la agregó
    valores: dict[str, str | None]


def _limpiar(columna: str, valor: str | None) -> str:
    """Normaliza lo digitado como lo entrega la extracción (monto sin puntos, RUT en mayúsculas, fecha ISO)."""
    texto = (valor or "").strip()
    if columna == "monto_solicitado":
        return re.sub(r"[.\s$]", "", texto)
    if columna == "rut":
        return re.sub(r"[.\s]", "", texto).upper()
    if columna == "fecha_oficio":
        coincidencia = _DIA_MES_ANIO.match(texto)
        if coincidencia:
            dia, mes, anio = coincidencia.groups()
            return f"{anio}-{int(mes):02d}-{int(dia):02d}"
    return texto


def _archivo(conexion: Connection, id_archivo: int) -> tuple[DocumentoPendiente, str]:
    fila = conexion.execute(text(
        "SELECT id_archivo, nombre_archivo, tipo_documento, ruta_original, fecha_recepcion, remitente, "
        "asunto_correo, estado_archivo FROM dbo.Archivos_TGR WHERE id_archivo = :id"
    ), {"id": id_archivo}).one_or_none()
    if fila is None:
        raise ExcepcionNoEncontrada(f"No existe el informe #{id_archivo}.")
    return DocumentoPendiente(*fila[:7]), fila[7]


def _historial(conexion: Connection, id_archivo: int) -> list[dict]:
    filas = conexion.execute(text(
        "SELECT r.id_revision, r.estado, r.observacion, r.cambios, r.fecha, u.nombre_completo AS usuario "
        "FROM etl.revisiones_documento r JOIN dbo.Usuarios u ON u.id_usuario = r.id_usuario "
        "WHERE r.id_archivo = :id ORDER BY r.id_revision DESC"
    ), {"id": id_archivo}).mappings().all()
    return [{**fila, "cambios": json.loads(fila["cambios"]) if fila["cambios"] else None,
             "id_caso_nuevo": None} for fila in filas]


def detalle(conexion: Connection, id_archivo: int) -> dict:
    """Informe con error: motivo, totales declarados, filas leídas con su confianza, historial y documento."""
    with transaccion(conexion):
        resumen = _resumen(conexion, DOCUMENTO, id_archivo)
        documento, estado_archivo = _archivo(conexion, id_archivo)
        guardada = cargar_extraccion(conexion, id_archivo)
        historial = _historial(conexion, id_archivo)
        confianza = conexion.execute(text("SELECT confianza_extraccion FROM dbo.Archivos_TGR WHERE id_archivo = :id"),
                                     {"id": id_archivo}).scalar_one()
    datos = {
        "nombre_archivo": documento.nombre_archivo, "tipo_documento": documento.tipo_documento,
        "estado_archivo": estado_archivo, "fecha_recepcion": documento.fecha_recepcion,
        "confianza_extraccion": confianza,
        "columnas": [{"campo": c, "etiqueta": ETIQUETAS[c], "critico": c in CAMPOS_CRITICOS}
                     for c in COLUMNAS_PLANTILLA],
        "umbral_confianza": UMBRAL_CONFIANZA,
        "extraccion": None if guardada is None else {
            "lote": guardada.lote, "fecha_documento": guardada.fecha_documento,
            "cantidad_declarada": guardada.cantidad_declarada, "suma_declarada": guardada.suma_declarada,
            "errores": guardada.errores, "observaciones": guardada.observaciones,
            "filas": [{"orden": f.orden, "valores": f.valores, "confianzas": f.confianzas} for f in guardada.filas],
        },
    }
    return {**resumen, "datos": datos, "historial": historial,
            "documento": {"nombre_buscado": documento.nombre_archivo, "id_archivo": id_archivo}}


def documento_original(conexion: Connection, id_archivo: int) -> DocumentoOriginal:
    with transaccion(conexion):
        _resumen(conexion, DOCUMENTO, id_archivo)
        documento, _ = _archivo(conexion, id_archivo)
    return DocumentoOriginal(documento.id_archivo, documento.nombre_archivo, documento.ruta_original)


def _estado_actual(conexion: Connection, id_archivo: int) -> str:
    """Estado vigente, bloqueando el informe hasta el fin de la transacción (dos analistas a la vez)."""
    estado = conexion.execute(text(
        "SELECT TOP 1 estado FROM etl.revisiones_documento WITH (UPDLOCK, HOLDLOCK) WHERE id_archivo = :id "
        "ORDER BY id_revision DESC"
    ), {"id": id_archivo}).scalar_one_or_none()
    return estado or PENDIENTE


def _registrar(conexion: Connection, id_archivo: int, estado: str, observacion: str,
               cambios: dict | None = None) -> int:
    id_usuario = bitacora.id_usuario_sistema(conexion)  # sin inicio de sesión todavía (RF09)
    id_revision = conexion.execute(text(
        "INSERT INTO etl.revisiones_documento (id_archivo, estado, observacion, cambios, id_usuario) "
        "OUTPUT INSERTED.id_revision VALUES (:id, :estado, :observacion, :cambios, :usuario)"
    ), {"id": id_archivo, "estado": estado, "observacion": observacion, "usuario": id_usuario,
        "cambios": json.dumps(cambios, ensure_ascii=False) if cambios else None}).scalar_one()
    bitacora.registrar(conexion, "Revisión de excepción", {
        "tipo": DOCUMENTO, "id": id_archivo, "estado": estado, "observacion": observacion,
        "cambios": sorted(cambios) if cambios else [],
    }, id_usuario)
    return id_revision


def revisar_documento(conexion: Connection, id_archivo: int, accion: str, observacion: str | None) -> str:
    """Descarta el informe o lo deja pendiente (también para reabrir uno descartado). Devuelve el estado."""
    if accion not in (DESCARTAR, DEJAR_PENDIENTE):
        raise DatosInvalidos(f"Acción no válida para un informe: {accion}.", "accion")
    nota = _observacion(observacion)
    with transaccion(conexion):
        _resumen(conexion, DOCUMENTO, id_archivo)
        _, estado_archivo = _archivo(conexion, id_archivo)
        if _estado_actual(conexion, id_archivo) == RESUELTO or estado_archivo != ERROR_EXTRACCION:
            raise AccionNoPermitida("El informe ya no está con error de extracción.")
        estado = DESCARTADO if accion == DESCARTAR else PENDIENTE
        _registrar(conexion, id_archivo, estado, nota)
    return estado


def volver_a_extraer(conexion: Connection, id_archivo: int, observacion: str | None) -> None:
    """Deja el informe 'Pendiente de Extracción' para que el proceso de extracción lo lea otra vez (OCR)."""
    nota = _observacion(observacion)
    with transaccion(conexion):
        _resumen(conexion, DOCUMENTO, id_archivo)
        _estado_actual(conexion, id_archivo)
        cambiados = conexion.execute(text(
            "UPDATE dbo.Archivos_TGR SET estado_archivo = :pendiente WHERE id_archivo = :id AND estado_archivo = :error"
        ), {"pendiente": PENDIENTE_EXTRACCION, "error": ERROR_EXTRACCION, "id": id_archivo}).rowcount
        if not cambiados:
            raise AccionNoPermitida("El informe ya no está con error de extracción.")
        _registrar(conexion, id_archivo, PENDIENTE, f"Se pidió volver a extraer el documento. {nota}")


def _resumen_fila(valores: dict[str, str]) -> str:
    return ", ".join(f"{ETIQUETAS[c]} {valores.get(c) or '—'}" for c in ("rut", "monto_solicitado"))


def _reconstruir(documento: DocumentoPendiente, guardada: ExtraccionGuardada, filas: list[FilaCorregida],
                 cantidad_declarada: int | None, suma_declarada: int | None) -> tuple[ResultadoExtraccion, dict]:
    """Informe con las correcciones del analista y qué cambió respecto de lo que leyó la extracción."""
    originales = {f.orden: f for f in guardada.filas}
    cambios: dict[str, dict] = {}
    registros, nuevas, usados = [], 0, set()
    for fila in filas:
        valores = {c: _limpiar(c, (fila.valores or {}).get(c)) for c in COLUMNAS_PLANTILLA}
        base = originales.get(fila.orden) if fila.orden is not None else None
        if fila.orden is not None and (base is None or fila.orden in usados):
            raise DatosInvalidos("La fila no existe en lo extraído: recargue la pantalla.")
        if base is None:
            nuevas += 1
            cambios[f"Fila nueva {nuevas}"] = {"antes": None, "despues": _resumen_fila(valores)}
            confianzas = {c: 100.0 for c in COLUMNAS_PLANTILLA}
        else:
            usados.add(base.orden)
            confianzas = {}
            for c in COLUMNAS_PLANTILLA:
                antes = (base.valores.get(c) or "").strip()
                if valores[c] != antes:
                    cambios[f"Fila {base.orden} · {ETIQUETAS[c]}"] = {"antes": antes, "despues": valores[c]}
                    confianzas[c] = 100.0  # lo verificó el analista
                else:
                    confianzas[c] = base.confianzas.get(c, 0.0)
        registros.append(RegistroExtraido(valores, confianzas))
    for orden, base in originales.items():
        if orden not in usados:
            cambios[f"Fila {orden}"] = {"antes": _resumen_fila(base.valores), "despues": "quitada"}
    for etiqueta, antes, despues in (("Cantidad de registros declarada", guardada.cantidad_declarada, cantidad_declarada),
                                     ("Monto total declarado", guardada.suma_declarada, suma_declarada)):
        if antes != despues:
            cambios[etiqueta] = {"antes": antes, "despues": despues}
    resultado = ResultadoExtraccion(
        tipo_documento=documento.tipo_documento, registros=registros, lote=guardada.lote,
        fecha_documento=guardada.fecha_documento, cantidad_declarada=cantidad_declarada,
        suma_declarada=suma_declarada,
    )
    return resultado, cambios


def procesar_corregido(conexion: Connection, id_archivo: int, observacion: str | None, filas: list[FilaCorregida],
                       cantidad_declarada: int | None, suma_declarada: int | None, almacen) -> int:
    """Envía al ETL el informe corregido. Si los totales siguen sin cuadrar, no carga nada. Devuelve los casos cargados."""
    nota = _observacion(observacion)
    if len(filas) > MAXIMO_FILAS:
        raise DatosInvalidos(f"Un informe admite hasta {MAXIMO_FILAS} filas.")
    for valor in (cantidad_declarada, suma_declarada):
        if valor is not None and valor < 0:
            raise DatosInvalidos("Los totales declarados no pueden ser negativos.")

    with transaccion(conexion):
        _resumen(conexion, DOCUMENTO, id_archivo)
        estado_revision = _estado_actual(conexion, id_archivo)
        documento, estado_archivo = _archivo(conexion, id_archivo)
        if estado_revision == RESUELTO or estado_archivo != ERROR_EXTRACCION:
            raise AccionNoPermitida("El informe ya no está con error de extracción.")
        if estado_revision == DESCARTADO:
            raise AccionNoPermitida("El informe está descartado: reábralo (dejar pendiente) antes de cargarlo.")
        guardada = cargar_extraccion(conexion, id_archivo) or ExtraccionGuardada(None, None, None, None, [], [], [])
        resultado, cambios = _reconstruir(documento, guardada, filas, cantidad_declarada, suma_declarada)
        if not resultado.registros:
            raise DatosInvalidos("El informe no trae deudores: agregue al menos una fila.")
        resultado.verificar_totales()
        if resultado.errores:
            raise DatosInvalidos(" ".join(resultado.errores) + " Corrija los montos o los totales declarados.")

        conexion.execute(text(
            "UPDATE dbo.Archivos_TGR SET estado_archivo = :estado, total_registros = :total, "
            "confianza_extraccion = :confianza WHERE id_archivo = :id"
        ), {"estado": NORMALIZADO, "total": len(resultado.registros), "confianza": resultado.confianza_promedio,
            "id": id_archivo})
        bitacora.registrar(conexion, "Extracción de documento", {
            "id_archivo": id_archivo, "nombre_archivo": documento.nombre_archivo, "estado": NORMALIZADO,
            "registros": len(resultado.registros), "corregido_manual": True, "errores": [],
            "observaciones": resultado.observaciones,
        })
        estado, motivo = cargar_en_etl(conexion, documento, resultado)
        if estado != "Procesado":
            raise DatosInvalidos(f"El ETL no aceptó el informe: {motivo}")
        _registrar(conexion, id_archivo, RESUELTO, nota, cambios)
    try:
        escribir_plantilla(resultado, ruta_plantilla(almacen / documento.ruta_original))
    except OSError:
        pass  # la plantilla es solo un respaldo del documento convertido; el informe ya quedó cargado
    # Fuera de la transacción: si la IA o el cruce fallan, el informe igual queda procesado (RF08, CU03 paso 6).
    analizar_sin_fallar(conexion, id_archivo)
    cruzar_sin_fallar(conexion, id_archivo)
    return len(resultado.registros)
