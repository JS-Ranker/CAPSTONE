"""Reglas de normalización de los casos TGR (RF02, RF03).

Reproduce, paso a paso, la transformación `Normalizar_TGR.ktr` (Base de datos/), que es la referencia:
Normalizacion -> Separar_Rol -> Separar_Tesoreria -> Norm_Tipo_Dato -> Normalizar_Mult_Rol /
Normalizar_Rev_Manual -> Validar_Indicadores -> Validar_RUT_DV -> Validar_Llave_Caso. La detección de
duplicados (Detectar_Duplicados) necesita ver todo el lote y la base, por eso está en `carga.py`.

Diferencias deliberadas con el .ktr, porque allá el paso simplemente falla o descarta en silencio:
- Una fecha o un monto que no se puede leer rechaza solo esa fila, con su motivo (en Pentaho, el
  `CSV file input` detiene la carga completa).
- Un valor más largo que su columna en core.casos_tgr rechaza la fila en vez de cortar la carga.
- Sin MONTO SOLICITADO la fila se rechaza (RN03 del ERS: el monto es obligatorio, y sin él no se puede
  calcular el descuento en el cruce). El .ktr lo deja pasar vacío.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

# Columnas del CSV, en el orden de transformacion_carga.ktr. El ETL de Pentaho lee por posición.
COLUMNAS_CSV = (
    "NOMBRE DOCUMENTO", "RUT", "DV", "ID DEMANDA*", "N° Resolución", "NOMBRE CLIENTE",
    "MONTO SOLICITADO", "SALDO", "TIPO EMBARGO", "EXPEDIENTE", "FECHA INGRESO CASILLA",
    "TESORERIA", "FECHA OFICIO", "MULTIPLES ROLES", "REVISION MANUAL", "CAMPOS FALTANTES OCR",
    "ENTIDAD BANCARIA", "id_correo", "remitente", "asunto", "RUTA DOCUMENTO",
)
# Mismo orden, con los nombres de stg.casos_tgr (recepcion_datos_input.sql).
COLUMNAS_STG = (
    "nombre_documento", "rut", "dv", "id_demanda", "n_resol", "nom_cli",
    "monto_solicitado", "saldo_menor_05_utm", "tipo_embargo", "rol", "fec_ing",
    "tesoreria", "fecha_oficio", "mult_rol", "rev_manual", "camp_falt",
    "ent_banco", "id_correo", "remit", "asunto", "ruta_doc",
)

# Expresiones de Separar_Rol y Separar_Tesoreria, copiadas del .ktr.
_ROL = re.compile(r"^\s*([0-9]+)\s*-\s*([0-9]{4})\s+(.+?)\s*$")
_TESORERIA = re.compile(r"^\s*TESORER[IÍ]A\s+(REGIONAL|PROVINCIAL)\s+(?:DE(?:L)?\s+)?(.+?)\s*$")
_INDICADORES = {"SI": True, "SÍ": True, "NO": False}  # Normalizar_Mult_Rol / Normalizar_Rev_Manual

# Largo máximo de cada texto en core.casos_tgr (creacion_tablas.sql).
_LARGOS = {
    "nom_cli": 250, "nombre_documento": 255, "id_demanda": 50, "n_resol": 50,
    "saldo_menor_05_utm": 30, "est_ret": 50, "rol": 200, "rol_cod": 30, "rol_loc": 150,
    "tesoreria": 200, "tesoreria_tipo": 15, "tesoreria_loc": 150, "camp_falt": 500,
    "ent_banco": 150, "id_correo": 255, "remit": 255, "asunto": 500, "ruta_doc": 1024,
}


@dataclass(frozen=True)
class Caso:
    """Una fila lista para core.casos_tgr. Las claves son los nombres de sus columnas."""
    columnas: dict

    @property
    def llave(self) -> tuple:
        """Llave de Detectar_Duplicados: RUT, DV, rol y fecha de ingreso."""
        c = self.columnas
        return (c["rut_limpio"], c["dv_limpio"], c["rol"], c["fec_ing"])


@dataclass(frozen=True)
class Rechazo:
    motivo: str


def _texto(valor: str | None, mayusculas: bool = False) -> str | None:
    """Paso Normalizacion: recorta espacios (y pasa a mayúsculas). Un texto vacío queda como nulo."""
    if valor is None:
        return None
    limpio = valor.strip()
    if mayusculas:
        limpio = limpio.upper()
    return limpio or None


def digito_verificador(rut: str) -> str:
    """DV por módulo 11, igual que el script de Validar_RUT_DV."""
    suma, multiplicador = 0, 2
    for cifra in reversed(rut):
        suma += int(cifra) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resultado = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resultado, str(resultado))


def limpiar_rut(rut: str | None, dv: str | None) -> tuple[str, str, bool]:
    """Validar_RUT_DV: quita puntos, guion y espacios; valida 7 a 9 dígitos y el DV."""
    rut_limpio = re.sub(r"[.\-\s]", "", rut or "")
    if rut_limpio.isdigit():
        rut_limpio = str(int(rut_limpio))  # el .ktr lee el RUT como número: sin ceros a la izquierda
    dv_limpio = (dv or "").strip().upper()
    valido = (
        re.fullmatch(r"[0-9]{7,9}", rut_limpio) is not None
        and re.fullmatch(r"[0-9K]", dv_limpio) is not None
        and digito_verificador(rut_limpio) == dv_limpio
    )
    return rut_limpio, dv_limpio, valido


def separar_rol(rol: str | None) -> tuple[str, int, str] | None:
    """Separar_Rol: '1532-2024 VALPARAÍSO' -> ('1532', 2024, 'VALPARAÍSO'). None si no calza."""
    coincidencia = _ROL.fullmatch(rol or "")
    if not coincidencia:
        return None
    codigo, anio, localidad = coincidencia.groups()
    return codigo, int(anio), localidad


def separar_tesoreria(tesoreria: str | None) -> tuple[str, str] | None:
    """Separar_Tesoreria: 'TESORERÍA PROVINCIAL DEL MAIPO' -> ('PROVINCIAL', 'MAIPO'). No rechaza la fila."""
    coincidencia = _TESORERIA.fullmatch(tesoreria or "")
    return coincidencia.groups() if coincidencia else None


def _fecha(valor: str | None) -> date | None:
    """Fechas del CSV en dd-MM-yyyy. Lanza ValueError si el formato no corresponde."""
    texto = _texto(valor)
    return datetime.strptime(texto, "%d-%m-%Y").date() if texto else None


def _monto(valor: str | None) -> Decimal | None:
    texto = _texto(valor)
    if texto is None:
        return None
    if not texto.isdigit():
        raise ValueError(texto)
    return Decimal(texto)


def normalizar(fila: dict[str, str | None]) -> Caso | Rechazo:
    """Aplica las reglas del .ktr a una fila de stg.casos_tgr (claves = COLUMNAS_STG)."""
    # Normalizar_Mult_Rol, Normalizar_Rev_Manual y Validar_Indicadores (van antes que la llave en el .ktr).
    indicadores = {}
    for campo, nombre in (("mult_rol", "MULTIPLES ROLES"), ("rev_manual", "REVISION MANUAL")):
        valor = _texto(fila.get(campo), mayusculas=True)
        if valor not in _INDICADORES:
            return Rechazo(f"{nombre} debe ser SI o NO (llegó: {valor or 'vacío'})")
        indicadores[campo] = _INDICADORES[valor]

    # Validar_RUT_DV y Validar_Llave_Caso: RUT y DV válidos, rol con formato y fecha de ingreso.
    rut_limpio, dv_limpio, rut_valido = limpiar_rut(fila.get("rut"), fila.get("dv"))
    if not rut_valido:
        return Rechazo(f"RUT o DV inválido ({fila.get('rut') or 'vacío'}-{fila.get('dv') or 'vacío'})")
    rol = _texto(fila.get("rol"), mayusculas=True)
    partes_rol = separar_rol(rol)
    if partes_rol is None:
        return Rechazo(f"EXPEDIENTE sin formato número-año localidad (llegó: {rol or 'vacío'})")
    try:
        fec_ing = _fecha(fila.get("fec_ing"))
    except ValueError:
        return Rechazo(f"FECHA INGRESO CASILLA no es dd-mm-aaaa (llegó: {fila.get('fec_ing')})")
    if fec_ing is None:
        return Rechazo("Falta FECHA INGRESO CASILLA")

    # Datos que en Pentaho harían fallar la carga completa: aquí se rechaza solo la fila.
    try:
        fecha_oficio = _fecha(fila.get("fecha_oficio"))
    except ValueError:
        return Rechazo(f"FECHA OFICIO no es dd-mm-aaaa (llegó: {fila.get('fecha_oficio')})")
    try:
        monto = _monto(fila.get("monto_solicitado"))
    except ValueError:
        return Rechazo(f"MONTO SOLICITADO no es un número entero (llegó: {fila.get('monto_solicitado')})")
    if monto is None:
        return Rechazo("Falta MONTO SOLICITADO")

    tesoreria = _texto(fila.get("tesoreria"), mayusculas=True)
    tesoreria_tipo, tesoreria_loc = separar_tesoreria(tesoreria) or (None, None)
    rol_cod, rol_anio, rol_loc = partes_rol
    columnas = {
        "rut_limpio": rut_limpio,
        "dv_limpio": dv_limpio,
        "nom_cli": _texto(fila.get("nom_cli"), mayusculas=True),
        "nombre_documento": _texto(fila.get("nombre_documento")),
        "id_demanda": _texto(fila.get("id_demanda")),
        "n_resol": _texto(fila.get("n_resol")),
        "monto_solicitado": monto,
        "saldo_menor_05_utm": _texto(fila.get("saldo_menor_05_utm")),
        "est_ret": _texto(fila.get("tipo_embargo"), mayusculas=True),  # Select values: TIPO EMBARGO -> est_ret
        "rol": rol,
        "rol_cod": rol_cod,
        "rol_anio": rol_anio,
        "rol_loc": rol_loc,
        "fec_ing": fec_ing,
        "fecha_oficio": fecha_oficio,
        "tesoreria": tesoreria,
        "tesoreria_tipo": tesoreria_tipo,
        "tesoreria_loc": tesoreria_loc,
        "mult_rol_bit": indicadores["mult_rol"],
        "rev_manual_bit": indicadores["rev_manual"],
        "camp_falt": _texto(fila.get("camp_falt"), mayusculas=True),
        "ent_banco": _texto(fila.get("ent_banco")),
        "id_correo": fila.get("id_correo") or None,  # sin recortar, como en el .ktr
        "remit": fila.get("remit") or None,
        "asunto": fila.get("asunto") or None,
        "ruta_doc": _texto(fila.get("ruta_doc")),
    }
    for columna, largo in _LARGOS.items():
        valor = columnas[columna]
        if valor is not None and len(valor) > largo:
            return Rechazo(f"{columna} supera los {largo} caracteres")
    return Caso(columnas)


# Campos de un caso que el analista puede corregir en la revisión manual (CU05). La llave del caso
# (RUT, DV, rol y fecha de ingreso) no se edita: cambiarla sería otro caso.
CAMPOS_CORREGIBLES = ("nom_cli", "id_demanda", "n_resol", "monto_solicitado", "fecha_oficio", "tesoreria", "ent_banco")


class CorreccionInvalida(ValueError):
    """Un valor corregido no cumple las reglas del ETL. `campo` indica cuál."""

    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


def corregir_campos(cambios: dict[str, str | None]) -> dict:
    """Valida y normaliza las correcciones de un caso con las mismas reglas del ETL.

    Recibe texto (fechas dd-mm-aaaa, montos sin puntos). Devuelve los valores para core.casos_tgr;
    si cambia la tesorería, también su tipo y localidad. Lanza CorreccionInvalida.
    """
    desconocidos = set(cambios) - set(CAMPOS_CORREGIBLES)
    if desconocidos:
        raise CorreccionInvalida(sorted(desconocidos)[0], "Este campo no se puede corregir.")
    valores = {}
    for campo, valor in cambios.items():
        if campo == "fecha_oficio":
            try:
                valores[campo] = _fecha(valor)
            except ValueError:
                raise CorreccionInvalida(campo, "La fecha debe ser dd-mm-aaaa.") from None
        elif campo == "monto_solicitado":
            try:
                valores[campo] = _monto(valor)
            except ValueError:
                raise CorreccionInvalida(campo, "El monto debe ser un número entero, sin puntos.") from None
            if valores[campo] is None:
                raise CorreccionInvalida(campo, "El monto es obligatorio.")
        elif campo in ("nom_cli", "tesoreria"):
            valores[campo] = _texto(valor, mayusculas=True)
        else:
            valores[campo] = _texto(valor)
        if isinstance(valores[campo], str) and len(valores[campo]) > _LARGOS[campo]:
            raise CorreccionInvalida(campo, f"Máximo {_LARGOS[campo]} caracteres.")
    if "tesoreria" in valores:
        valores["tesoreria_tipo"], valores["tesoreria_loc"] = separar_tesoreria(valores["tesoreria"]) or (None, None)
    return valores
