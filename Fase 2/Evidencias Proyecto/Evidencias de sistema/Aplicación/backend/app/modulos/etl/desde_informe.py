"""Convierte los deudores extraídos de un informe de la TGR en filas del ETL (las 21 columnas de stg.casos_tgr).

El informe trae los datos del deudor (RUT, nombre, demanda, resolución, monto, tipo de embargo, expediente,
tesorería y fecha del oficio). El resto de las columnas del CSV de Tomás las agrega el proceso:
- FECHA INGRESO CASILLA y NOMBRE DOCUMENTO: la fecha en que llegó el informe.
- MULTIPLES ROLES: el mismo RUT aparece más de una vez en el informe.
- CAMPOS FALTANTES OCR y REVISION MANUAL: campos vacíos o leídos con confianza bajo el umbral (RN05). Estos
  casos se cargan igual y quedan en la Bandeja de Excepciones para que el analista los revise.
- ENTIDAD BANCARIA, remitente, asunto y RUTA DOCUMENTO: de la recepción del informe.
"""
import re
from collections import Counter
from datetime import datetime

from ..extraccion.plantilla import CAMPOS_CRITICOS, COLUMNAS_PLANTILLA, UMBRAL_CONFIANZA, ResultadoExtraccion

ENTIDAD_BANCARIA = "BANCO GENÉRICO"
# Nombre de cada columna del informe tal como aparece en CAMPOS FALTANTES OCR.
TITULOS = {
    "rut": "RUT", "nombre": "NOMBRE CLIENTE", "id_demanda": "ID DEMANDA", "n_resolucion": "N° RESOLUCIÓN",
    "monto_solicitado": "MONTO SOLICITADO", "tipo_embargo": "TIPO EMBARGO", "expediente": "EXPEDIENTE",
    "tesoreria": "TESORERIA", "fecha_oficio": "FECHA OFICIO",
}
_RUT = re.compile(r"^(\d{1,9})-([\dK])$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _rut_y_dv(valor: str) -> tuple[str, str]:
    """'12345678-K' -> ('12345678', 'K'). Si no tiene ese formato, el RUT queda tal cual y el ETL lo rechaza."""
    coincidencia = _RUT.match(valor or "")
    return coincidencia.groups() if coincidencia else (valor or "", "")


def _fecha_ddmmaaaa(valor: str) -> str:
    """La extracción entrega fechas ISO; el ETL las espera dd-mm-aaaa. Lo que no es fecha queda tal cual."""
    coincidencia = _ISO.match(valor or "")
    if not coincidencia:
        return valor or ""
    anio, mes, dia = coincidencia.groups()
    return f"{dia}-{mes}-{anio}"


def campos_dudosos(valores: dict[str, str], confianzas: dict[str, float]) -> list[str]:
    """Columnas vacías, o críticas leídas con confianza bajo el umbral (RN05), en el orden del informe.

    La confianza se exige solo en los campos críticos (RUT, monto y expediente): una tesorería algo borrosa
    no impide el cruce, pero un monto dudoso sí cambia el descuento.
    """
    return [TITULOS[c] for c in COLUMNAS_PLANTILLA
            if not (valores.get(c) or "").strip()
            or (c in CAMPOS_CRITICOS and confianzas.get(c, 0.0) < UMBRAL_CONFIANZA)]


def filas_para_etl(resultado: ResultadoExtraccion, *, nombre_archivo: str, fecha_recepcion: datetime,
                   remitente: str | None = None, asunto: str | None = None) -> list[dict[str, str]]:
    ruts = Counter(registro.valores.get("rut", "") for registro in resultado.registros)
    filas = []
    for registro in resultado.registros:
        v = registro.valores
        rut, dv = _rut_y_dv(v.get("rut", ""))
        dudosos = campos_dudosos(v, registro.confianzas)
        filas.append({
            "nombre_documento": f"{fecha_recepcion:%Y%m%d}",  # transformacion_carga.ktr lo lee como fecha
            "rut": rut,
            "dv": dv,
            "id_demanda": v.get("id_demanda", ""),
            "n_resol": v.get("n_resolucion", ""),
            "nom_cli": v.get("nombre", ""),
            "monto_solicitado": v.get("monto_solicitado", ""),
            "saldo_menor_05_utm": "",  # lo define el cruce con el banco, no el informe
            "tipo_embargo": v.get("tipo_embargo", ""),
            "rol": v.get("expediente", ""),
            "fec_ing": f"{fecha_recepcion:%d-%m-%Y}",
            "tesoreria": v.get("tesoreria", ""),
            "fecha_oficio": _fecha_ddmmaaaa(v.get("fecha_oficio", "")),
            "mult_rol": "SI" if v.get("rut") and ruts[v.get("rut")] > 1 else "NO",
            "rev_manual": "SI" if dudosos else "NO",
            "camp_falt": ", ".join(dudosos),
            "ent_banco": ENTIDAD_BANCARIA,
            "id_correo": "",
            "remit": remitente or "",
            "asunto": asunto or "",
            "ruta_doc": nombre_archivo,
        })
    return filas
