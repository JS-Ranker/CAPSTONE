"""Plantilla estándar de carga y resultado de la extracción (RF12, RN05, CU12).

La plantilla es la interfaz con el ETL: encabezado, fila de columnas, detalle y pie de totales.
Es la propuesta v1 descrita en data/simulados/README.md.
"""
import csv
from dataclasses import dataclass, field
from pathlib import Path

COLUMNAS_PLANTILLA = (
    "id_transaccion", "rut_deudor", "nombre_deudor", "folio_deuda", "monto",
    "fecha_origen", "cuenta_destino", "codigo_banco", "tipo_movimiento",
)
CAMPOS_CRITICOS = ("rut_deudor", "monto", "cuenta_destino")  # RN05
UMBRAL_CONFIANZA = 90.0  # RN05: confianza mínima en los campos críticos

NORMALIZADO, ERROR_EXTRACCION = "Normalizado", "Error de Extracción"  # estados de Archivos_TGR


@dataclass
class RegistroExtraido:
    valores: dict[str, str]
    confianzas: dict[str, float]  # 0-100 por columna; 100 cuando el texto viene del documento

    @property
    def confianza(self) -> float:
        """Confianza del registro: la del campo crítico menos confiable (RN05)."""
        return min(self.confianzas.get(campo, 0.0) for campo in CAMPOS_CRITICOS)

    @property
    def requiere_revision(self) -> bool:
        """Va a la Bandeja de Excepciones como "Revisión de Extracción" (RN05)."""
        return self.confianza < UMBRAL_CONFIANZA


@dataclass
class ResultadoExtraccion:
    tipo_documento: str  # 'PDF con texto', 'PDF escaneado' o 'Imagen' (Archivos_TGR)
    registros: list[RegistroExtraido] = field(default_factory=list)
    lote: str | None = None
    fecha_documento: str | None = None
    cantidad_declarada: int | None = None
    suma_declarada: int | None = None
    errores: list[str] = field(default_factory=list)  # impiden usar el documento: revisión manual
    observaciones: list[str] = field(default_factory=list)  # informativas

    @property
    def estado(self) -> str:
        return ERROR_EXTRACCION if self.errores else NORMALIZADO

    @property
    def confianza_promedio(self) -> float | None:
        if not self.registros:
            return None
        return round(sum(r.confianza for r in self.registros) / len(self.registros), 2)

    @property
    def suma_extraida(self) -> int:
        montos = (r.valores["monto"] for r in self.registros)
        return sum(int(monto) for monto in montos if monto.isdigit())

    def verificar_totales(self) -> None:
        """Compara el detalle con las sumatorias de control del documento, si existen (RN05, CU12 5b)."""
        if self.cantidad_declarada is None and self.suma_declarada is None:
            self.observaciones.append("El documento no trae sumatorias de control: no se pudo verificar.")
            return
        if self.cantidad_declarada is not None and self.cantidad_declarada != len(self.registros):
            self.errores.append(f"El documento declara {self.cantidad_declarada} registros y se extrajeron "
                                f"{len(self.registros)}.")
        if self.suma_declarada is not None and self.suma_declarada != self.suma_extraida:
            self.errores.append(f"El documento declara un monto total de {self.suma_declarada} y la suma del "
                                f"detalle extraído es {self.suma_extraida}.")


def escribir_plantilla(resultado: ResultadoExtraccion, ruta: Path) -> None:
    """Escribe el documento convertido a la plantilla estándar (CSV UTF-8 separado por ';')."""
    if resultado.estado != NORMALIZADO:
        raise ValueError(f"El documento tiene errores de extracción y debe revisarse a mano: {resultado.errores}")
    cantidad = len(resultado.registros)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(["ENCABEZADO", "TGR", resultado.lote or "", resultado.fecha_documento or "", cantidad])
        escritor.writerow(COLUMNAS_PLANTILLA)
        escritor.writerows([r.valores[c] for c in COLUMNAS_PLANTILLA] for r in resultado.registros)
        escritor.writerow(["TOTALES", cantidad, resultado.suma_extraida])
