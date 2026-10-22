"""Carga el core bancario simulado de Banco Genérico (banco.cuentas) desde un CSV.

Formato (UTF-8, separado por ';'): rut_titular;cuenta;codigo_banco;tipo_cuenta;saldo;estado_cuenta
El archivo de data/simulados/banco_generico/ lo genera scripts/generar_datos_simulados.py.

Las cuentas se identifican por su número: si ya existe, se actualizan su saldo, tipo y estado (los cruces ya hechos
conservan el saldo con que se calcularon). Las cuentas que no vienen en el archivo no se tocan.
"""
import csv
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import Connection, text

from ... import bitacora
from ...db import transaccion

COLUMNAS = ("rut_titular", "cuenta", "codigo_banco", "tipo_cuenta", "saldo", "estado_cuenta")
TIPOS = ("Cuenta RUT", "Cuenta corriente", "Chequera electrónica", "Cuenta de ahorro")
ESTADOS = ("Activa", "Bloqueada", "Cerrada")
_RUT = re.compile(r"^(\d{1,9})-([\dK])$")


class ErrorCoreBancario(ValueError):
    pass


@dataclass(frozen=True)
class ResumenCarga:
    nuevas: int
    actualizadas: int


def leer(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo, delimiter=";")
        if tuple(lector.fieldnames or ()) != COLUMNAS:
            raise ErrorCoreBancario(f"El encabezado debe ser: {';'.join(COLUMNAS)}")
        cuentas = []
        for numero, fila in enumerate(lector, start=2):
            rut = _RUT.match(fila["rut_titular"].strip().upper().replace(".", ""))
            if not rut:
                raise ErrorCoreBancario(f"Fila {numero}: RUT {fila['rut_titular']!r} sin formato 12345678-9.")
            try:
                saldo = Decimal(fila["saldo"])
            except InvalidOperation as error:
                raise ErrorCoreBancario(f"Fila {numero}: saldo {fila['saldo']!r} no es un número.") from error
            if saldo < 0 or fila["tipo_cuenta"] not in TIPOS or fila["estado_cuenta"] not in ESTADOS:
                raise ErrorCoreBancario(f"Fila {numero}: saldo negativo, tipo o estado de cuenta desconocido.")
            cuentas.append({"rut": rut.group(1), "dv": rut.group(2), "numero": fila["cuenta"].strip(),
                            "tipo": fila["tipo_cuenta"], "saldo": saldo, "estado": fila["estado_cuenta"]})
    return cuentas


def cargar(conexion: Connection, cuentas: list[dict], origen: str) -> ResumenCarga:
    with transaccion(conexion):
        existentes = {numero for (numero,) in conexion.execute(text("SELECT numero_cuenta FROM banco.cuentas"))}
        nuevas = [c for c in cuentas if c["numero"] not in existentes]
        actualizadas = [c for c in cuentas if c["numero"] in existentes]
        if nuevas:
            conexion.execute(
                text("INSERT INTO banco.cuentas (rut, dv, numero_cuenta, tipo_cuenta, saldo, estado) "
                     "VALUES (:rut, :dv, :numero, :tipo, :saldo, :estado)"), nuevas)
        if actualizadas:
            conexion.execute(
                text("UPDATE banco.cuentas SET rut = :rut, dv = :dv, tipo_cuenta = :tipo, saldo = :saldo, "
                     "estado = :estado WHERE numero_cuenta = :numero"), actualizadas)
        resumen = ResumenCarga(len(nuevas), len(actualizadas))
        bitacora.registrar(conexion, "Carga del core bancario simulado",
                           {"origen": origen, "nuevas": resumen.nuevas, "actualizadas": resumen.actualizadas})
    return resumen
