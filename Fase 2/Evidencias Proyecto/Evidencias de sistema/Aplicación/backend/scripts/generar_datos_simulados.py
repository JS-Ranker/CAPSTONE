"""Genera las nóminas TGR simuladas para desarrollar y probar TTDH Automation.

Crea documentos ficticios en todos los formatos del alcance (Excel, CSV, TXT, PDF con texto,
PDF escaneado y fotografía), con casos válidos y casos de borde, una base simulada de cuentas
de Banco Genérico para el cruce y un manifiesto con el resultado esperado de cada archivo y
registro, que sirve como referencia para las pruebas de cada módulo.

Uso, desde la carpeta backend/:
    python scripts/generar_datos_simulados.py                 # escribe en ../data/simulados
    python scripts/generar_datos_simulados.py --grande 12000  # agrega una nómina de volumen

Con la misma semilla el resultado es siempre el mismo. Solo se sobrescriben los archivos que
genera este script; nunca se borra nada de la carpeta de salida.

Los RUT se generan entre 40.000.000 y 49.999.999, fuera de los rangos que hoy se asignan a
personas (bajo 30 millones) y empresas (desde 50 millones), para no asociar por accidente a
una persona real con una deuda.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from fpdf import FPDF
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

CARPETA_SALIDA = Path(__file__).resolve().parents[2] / "data" / "simulados"

# Plantilla estándar de carga (propuesta v1): encabezado, fila de columnas, detalle y pie.
COLUMNAS = (
    "id_transaccion", "rut_deudor", "nombre_deudor", "folio_deuda", "monto",
    "fecha_origen", "cuenta_destino", "codigo_banco", "tipo_movimiento",
)
TIPOS_MOVIMIENTO = ("Depósito", "Devolución", "Traspaso")
CODIGO_BANCO_GENERICO = "099"
FECHA_GENERACION = date(2026, 10, 1)
FECHA_METADATOS = datetime(2026, 10, 1, 9, 0)  # fija, para que los archivos sean reproducibles
AVISO = "DOCUMENTO SIMULADO - SIN VALIDEZ - SOLO PARA PRUEBAS"

VALIDO, INVALIDO, DUPLICADO, REVISION = "Válido", "Inválido", "Duplicado", "Revisión de Extracción"

NOMBRES = (
    "María", "José", "Juan", "Camila", "Francisca", "Benjamín", "Sofía", "Matías", "Valentina",
    "Tomás", "Javiera", "Agustín", "Constanza", "Vicente", "Antonia", "Joaquín", "Catalina",
    "Ignacio", "Fernanda", "Sebastián",
)
APELLIDOS = (
    "González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras", "Silva", "Martínez",
    "Sepúlveda", "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres", "Araya",
    "Flores", "Espinoza", "Valenzuela", "Castillo", "Núñez", "Ibáñez", "Peña",
)


def digito_verificador(numero: int) -> str:
    """Dígito verificador del RUT según el algoritmo Módulo 11 (RN01)."""
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resto, str(resto))


def rut_con_puntos(rut: str) -> str:
    numero, dv = rut.split("-")
    return f"{int(numero):,}".replace(",", ".") + f"-{dv}"


def formato_clp(monto: int) -> str:
    return "$ " + f"{monto:,}".replace(",", ".")


@dataclass
class Registro:
    """Una transacción del detalle, con sus valores normalizados y el resultado esperado."""

    id_transaccion: str
    rut: str
    nombre: str
    folio: str
    monto: int | None
    fecha: date | None
    cuenta: str
    banco: str
    tipo: str
    # Cómo aparece un campo en el archivo cuando difiere del valor normalizado (casos de borde).
    escrito: dict[str, str] = field(default_factory=dict)
    estado: str = VALIDO
    motivo: str | None = None
    caso: str | None = None

    def normalizado(self) -> dict[str, object]:
        return {
            "id_transaccion": self.id_transaccion,
            "rut_deudor": self.rut,
            "nombre_deudor": self.nombre,
            "folio_deuda": self.folio,
            "monto": self.monto,
            "fecha_origen": self.fecha.isoformat() if self.fecha else None,
            "cuenta_destino": self.cuenta,
            "codigo_banco": self.banco,
            "tipo_movimiento": self.tipo,
        }

    def texto(self, columna: str) -> str:
        """Valor tal como se escribe en los archivos estructurados."""
        if columna in self.escrito:
            return self.escrito[columna]
        valor = self.normalizado()[columna]
        return "" if valor is None else str(valor)

    def texto_impreso(self, columna: str) -> str:
        """Valor tal como se imprime en los PDF e imágenes (formato chileno)."""
        if columna in self.escrito:
            return self.escrito[columna]
        if columna == "rut_deudor" and self.rut:
            return rut_con_puntos(self.rut)
        if columna == "monto" and self.monto is not None:
            return formato_clp(self.monto)
        if columna == "fecha_origen" and self.fecha:
            return self.fecha.strftime("%d-%m-%Y")
        return self.texto(columna)

    def para_manifiesto(self) -> dict[str, object]:
        fila = {**self.normalizado(), "estado_esperado": self.estado}
        if self.motivo:
            fila["motivo"] = self.motivo
        if self.caso:
            fila["caso"] = self.caso
        if self.escrito:
            fila["valor_en_archivo"] = dict(self.escrito)
        return fila


def copia(registro: Registro, **cambios: object) -> Registro:
    return replace(registro, escrito=dict(registro.escrito), **cambios)


@dataclass
class Nomina:
    lote: str
    registros: list[Registro]
    cantidad_declarada: int | None = None  # None: la cantidad real del detalle
    suma_declarada: int | None = None  # None: la suma real de los montos del detalle

    @property
    def cantidad(self) -> int:
        return len(self.registros) if self.cantidad_declarada is None else self.cantidad_declarada

    @property
    def suma(self) -> int:
        if self.suma_declarada is not None:
            return self.suma_declarada
        return sum(r.monto for r in self.registros if r.monto is not None)

    def encabezado(self) -> list[str]:
        return ["ENCABEZADO", "TGR", self.lote, FECHA_GENERACION.isoformat(), str(self.cantidad)]

    def pie(self) -> list[str]:
        return ["TOTALES", str(self.cantidad), str(self.suma)]


class Generador:
    """Produce registros ficticios reproducibles a partir de una semilla."""

    def __init__(self, semilla: int) -> None:
        self.rng = random.Random(semilla)
        self._ultimo_id = 98_000
        self._ultimo_folio = 772_000
        self._ultimo_lote = 0

    def lote(self) -> str:
        self._ultimo_lote += 1
        return f"LOTE-{FECHA_GENERACION:%Y%m%d}-{self._ultimo_lote:02d}"

    def rut(self, dv: str | None = None) -> str:
        while True:
            numero = self.rng.randint(40_000_000, 49_999_999)
            digito = digito_verificador(numero)
            if dv is None or digito == dv:
                return f"{numero}-{digito}"

    def registro(self) -> Registro:
        self._ultimo_id += self.rng.randint(1, 40)
        self._ultimo_folio += self.rng.randint(1, 30)
        return Registro(
            id_transaccion=f"TGR-{self._ultimo_id:07d}",
            rut=self.rut(),
            nombre=f"{self.rng.choice(NOMBRES)} {self.rng.choice(APELLIDOS)} {self.rng.choice(APELLIDOS)}",
            folio=f"F-{self._ultimo_folio}",
            monto=self.rng.randint(5_000, 3_000_000),
            fecha=FECHA_GENERACION - timedelta(days=self.rng.randint(1, 30)),
            cuenta=str(self.rng.randint(10**9, 10**10 - 1)),
            banco=CODIGO_BANCO_GENERICO,
            tipo=self.rng.choices(TIPOS_MOVIMIENTO, weights=(70, 20, 10))[0],
        )

    def registros(self, cantidad: int) -> list[Registro]:
        return [self.registro() for _ in range(cantidad)]

    def nomina(self, cantidad: int) -> Nomina:
        return Nomina(self.lote(), self.registros(cantidad))


def casos_de_borde(gen: Generador) -> list[Registro]:
    """Registros válidos de base más un caso por cada regla de validación (RN01-RN03, RF03)."""
    registros = gen.registros(10)

    def agregar(caso: str, estado: str = VALIDO, motivo: str | None = None) -> Registro:
        registro = gen.registro()
        registro.caso, registro.estado, registro.motivo = caso, estado, motivo
        registros.append(registro)
        return registro

    r = agregar("RUT con puntos")
    r.escrito["rut_deudor"] = rut_con_puntos(r.rut)
    r = agregar("RUT con dígito verificador k minúscula")
    r.rut = gen.rut(dv="K")
    r.escrito["rut_deudor"] = r.rut.lower()
    r = agregar("RUT con espacios alrededor")
    r.escrito["rut_deudor"] = f"  {r.rut} "

    r = agregar("Dígito verificador incorrecto", INVALIDO, "RN01 - RUT no pasa Módulo 11")
    numero, dv = r.rut.split("-")
    r.rut = f"{numero}-{'1' if dv != '1' else '2'}"
    r = agregar("RUT con letras en el número", INVALIDO, "RN01 - RUT con formato inválido")
    r.rut = r.rut[:2] + "A" + r.rut[3:]
    r = agregar("RUT vacío", INVALIDO, "RN01 - RUT con formato inválido")
    r.rut = ""

    r = agregar("Sin monto", INVALIDO, "RN03 - Falta monto")
    r.monto = None
    r = agregar("Sin cuenta de destino", INVALIDO, "RN03 - Falta cuenta_destino")
    r.cuenta = ""
    r = agregar("Sin código de banco", INVALIDO, "RN03 - Falta codigo_banco")
    r.banco = ""
    r = agregar("Sin tipo de movimiento", INVALIDO, "RN03 - Falta tipo_movimiento")
    r.tipo = ""

    r = agregar("Monto con formato de moneda")
    r.escrito["monto"] = formato_clp(r.monto)
    r = agregar("Monto escrito en palabras", INVALIDO, "RF03 - Monto con formato inválido")
    r.monto = None
    r.escrito["monto"] = "mil pesos"
    r = agregar("Fecha dd-mm-aaaa")
    r.escrito["fecha_origen"] = r.fecha.strftime("%d-%m-%Y")
    r = agregar("Fecha dd/mm/aaaa")
    r.escrito["fecha_origen"] = r.fecha.strftime("%d/%m/%Y")
    r = agregar("Fecha inexistente", INVALIDO, "RF03 - Fecha inválida")
    r.fecha = None
    r.escrito["fecha_origen"] = "31-02-2026"
    r = agregar("Tipo de movimiento desconocido", INVALIDO, "RF03 - Tipo de movimiento no reconocido")
    r.tipo = "Abono"

    r = agregar("Nombre con ñ y tildes")
    r.nombre = "Begoña Ñancupil Ibáñez"
    r = agregar("Sin nombre: no es campo obligatorio según RN03")
    r.nombre = ""
    r = agregar("Sin folio: no es campo obligatorio según RN03")
    r.folio = ""

    original = registros[2]
    registros.append(copia(
        original, estado=DUPLICADO, caso="Repetición exacta de otro registro del mismo archivo",
        motivo=f"RN02 - Repite ID, RUT, monto y fecha de {original.id_transaccion}",
    ))
    parecido = registros[3]
    registros.append(copia(
        parecido, monto=parecido.monto + 1_000,
        caso=f"Mismo ID que {parecido.id_transaccion} pero otro monto: no es duplicado según la clave de RN02",
    ))
    return registros


# --------------------------------------------------------------- escritura de archivos


def escribir_delimitado(
    ruta: Path, nomina: Nomina, *, delimitador: str = ";", encoding: str = "utf-8",
    con_pie: bool = True, columnas: tuple[str, ...] = COLUMNAS, titulos: dict[str, str] | None = None,
) -> None:
    titulos = titulos or {}
    with ruta.open("w", encoding=encoding, newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=delimitador)
        escritor.writerow(nomina.encabezado())
        escritor.writerow([titulos.get(c, c) for c in columnas])
        escritor.writerows([r.texto(c) for c in columnas] for r in nomina.registros)
        if con_pie:
            escritor.writerow(nomina.pie())


def escribir_excel(ruta: Path, nomina: Nomina) -> None:
    """Montos y fechas válidos como celdas numéricas y de fecha, igual que un Excel real."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Nomina"
    hoja.append(nomina.encabezado())
    hoja.append(list(COLUMNAS))
    for registro in nomina.registros:
        fila: list[object] = [registro.texto(c) for c in COLUMNAS]
        if registro.monto is not None and "monto" not in registro.escrito:
            fila[COLUMNAS.index("monto")] = registro.monto
        if registro.fecha is not None and "fecha_origen" not in registro.escrito:
            fila[COLUMNAS.index("fecha_origen")] = registro.fecha
        hoja.append(fila)
    hoja.append(nomina.pie())
    libro.properties.creator = "TTDH Automation - datos simulados"
    libro.properties.created = FECHA_METADATOS
    libro.save(ruta)
    _fijar_fechas_xlsx(ruta)


def _fijar_fechas_xlsx(ruta: Path) -> None:
    """openpyxl graba la hora actual al guardar (en los metadatos y en el zip). Se reemplaza por
    una fija para que regenerar los datos no cambie los archivos."""
    modificado = FECHA_METADATOS.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    with zipfile.ZipFile(ruta) as original:
        entradas = [(info.filename, original.read(info)) for info in original.infolist()]
    with zipfile.ZipFile(ruta, "w") as nuevo:
        for nombre, datos in entradas:
            if nombre == "docProps/core.xml":
                datos = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>" + modificado, datos)
            info = zipfile.ZipInfo(nombre, date_time=FECHA_METADATOS.timetuple()[:6])
            nuevo.writestr(info, datos, compress_type=zipfile.ZIP_DEFLATED)


TITULOS_IMPRESOS = {
    "id_transaccion": "ID Transacción", "rut_deudor": "RUT Deudor", "nombre_deudor": "Nombre",
    "folio_deuda": "Folio", "monto": "Monto", "fecha_origen": "Fecha",
    "cuenta_destino": "Cuenta Destino", "codigo_banco": "Banco", "tipo_movimiento": "Tipo",
}


def escribir_pdf_texto(ruta: Path, nomina: Nomina) -> None:
    anchos_mm = (27, 27, 62, 20, 27, 22, 28, 14, 22)
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_creation_date(FECHA_METADATOS)
    pdf.set_title(f"Nómina de deudores {nomina.lote}")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, "Tesorería General de la República - Nómina de deudores", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, AVISO, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Lote: {nomina.lote}    Fecha de generación: {FECHA_GENERACION:%d-%m-%Y}    "
                   f"Registros: {nomina.cantidad}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 8)
    for columna, ancho in zip(COLUMNAS, anchos_mm):
        pdf.cell(ancho, 6, TITULOS_IMPRESOS[columna], border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for registro in nomina.registros:
        for columna, ancho in zip(COLUMNAS, anchos_mm):
            alineacion = "R" if columna == "monto" else "L"
            pdf.cell(ancho, 6, registro.texto_impreso(columna), border=1, align=alineacion)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"TOTALES    Registros: {nomina.cantidad}    Monto total: {formato_clp(nomina.suma)}")
    pdf.output(str(ruta))


def _fuente(tamano: int, negrita: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    nombres = ("arialbd.ttf", "DejaVuSans-Bold.ttf") if negrita else ("arial.ttf", "DejaVuSans.ttf")
    for nombre in nombres:
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default(size=tamano)


def dibujar_nomina(nomina: Nomina) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Dibuja la nómina como una hoja A4 apaisada a 200 dpi.

    Devuelve la imagen y el recuadro de la celda de monto de cada registro.
    """
    anchos = (230, 250, 520, 170, 230, 200, 230, 110, 200)
    imagen = Image.new("RGB", (2339, 1654), "white")
    lapiz = ImageDraw.Draw(imagen)
    x0, y = 100, 80
    lapiz.text((x0, y), "Tesorería General de la República - Nómina de deudores", font=_fuente(40, True), fill="black")
    y += 60
    lapiz.text((x0, y), AVISO, font=_fuente(24), fill="black")
    y += 40
    lapiz.text((x0, y), f"Lote: {nomina.lote}     Fecha de generación: {FECHA_GENERACION:%d-%m-%Y}     "
                        f"Registros: {nomina.cantidad}", font=_fuente(28), fill="black")
    y += 70
    alto_fila = 44
    filas = [[TITULOS_IMPRESOS[c] for c in COLUMNAS]] + [
        [r.texto_impreso(c) for c in COLUMNAS] for r in nomina.registros
    ]
    cajas_monto = []
    for indice, valores in enumerate(filas):
        fuente = _fuente(26, negrita=indice == 0)
        x = x0
        for columna, ancho, valor in zip(COLUMNAS, anchos, valores):
            caja = (x, y, x + ancho, y + alto_fila)
            lapiz.rectangle(caja, outline="black", width=2)
            lapiz.text((x + 10, y + 8), valor, font=fuente, fill="black")
            if columna == "monto" and indice > 0:
                cajas_monto.append(caja)
            x += ancho
        y += alto_fila
    y += 30
    lapiz.text((x0, y), f"TOTALES     Registros: {nomina.cantidad}     Monto total: {formato_clp(nomina.suma)}",
               font=_fuente(28, True), fill="black")
    return imagen, cajas_monto


def escribir_pdf_escaneado(ruta: Path, nomina: Nomina) -> None:
    """Simula un escaneo: gris, levemente girado, con ruido y algo de desenfoque."""
    hoja, _ = dibujar_nomina(nomina)
    gris = hoja.convert("L").rotate(0.6, resample=Image.Resampling.BICUBIC, fillcolor=255)
    gris = Image.blend(gris, Image.effect_noise(gris.size, 40), 0.08)
    gris = gris.filter(ImageFilter.GaussianBlur(0.5))
    gris.save(ruta, "PDF", resolution=200.0, title=f"Nómina escaneada {nomina.lote}",
              creationDate=FECHA_METADATOS.timetuple(), modDate=FECHA_METADATOS.timetuple())


def escribir_fotografia(ruta: Path, nomina: Nomina, filas_manchadas: list[int]) -> None:
    """Simula una foto de celular: perspectiva, sombra, bajo contraste, desenfoque y manchas.

    Una mancha uniforme no basta (el OCR la separa como si fuera fondo), así que el monto
    manchado además se corre: con ese desenfoque Tesseract deja de leerlo con confianza.
    """
    hoja, cajas_monto = dibujar_nomina(nomina)
    lapiz = ImageDraw.Draw(hoja, "RGBA")
    for fila in filas_manchadas:
        x1, y1, x2, y2 = cajas_monto[fila]
        zona = (x1 + 2, y1 + 2, x2 - 2, y2 - 2)
        hoja.paste(hoja.crop(zona).filter(ImageFilter.GaussianBlur(2.5)), zona[:2])
        lapiz.ellipse((x1 - 20, y1 - 12, x2 + 20, y2 + 12), fill=(120, 85, 40, 150))
    ancho, alto = hoja.size
    sombra = Image.linear_gradient("L").rotate(90).resize(hoja.size)
    foto = Image.composite(hoja, ImageEnhance.Brightness(hoja).enhance(0.6), sombra)
    esquinas = (  # superior izq., inferior izq., inferior der., superior der.
        ancho * 0.04, alto * 0.02, ancho * 0.01, alto * 0.97,
        ancho * 0.98, alto * 0.99, ancho * 0.98, alto * 0.05,
    )
    fondo = (70, 65, 60)
    foto = foto.transform(hoja.size, Image.Transform.QUAD, esquinas, Image.Resampling.BICUBIC, fillcolor=fondo)
    foto = foto.rotate(1.5, resample=Image.Resampling.BICUBIC, fillcolor=fondo)
    foto = ImageEnhance.Contrast(foto).enhance(0.7).filter(ImageFilter.GaussianBlur(1.1))
    foto = foto.resize((int(ancho * 0.75), int(alto * 0.75)), Image.Resampling.LANCZOS)
    foto.save(ruta, "JPEG", quality=60)


def escribir_cuentas_banco(ruta: Path, cuentas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=("rut_titular", "cuenta", "codigo_banco", "estado_cuenta"),
                                  delimiter=";")
        escritor.writeheader()
        escritor.writerows(cuentas)


# --------------------------------------------------------------- generación del conjunto


def entrada_manifiesto(
    ruta_relativa: str, tipo_documento: str, proposito: str, estado_archivo: str,
    nomina: Nomina | None = None, motivo: str | None = None, incluir_registros: bool = True,
) -> dict[str, object]:
    entrada: dict[str, object] = {
        "archivo": ruta_relativa,
        "tipo_documento": tipo_documento,
        "proposito": proposito,
        "estado_archivo_esperado": estado_archivo,
    }
    if motivo:
        entrada["motivo"] = motivo
    if nomina is not None:
        resumen: dict[str, int] = {}
        for registro in nomina.registros:
            resumen[registro.estado] = resumen.get(registro.estado, 0) + 1
        entrada |= {
            "lote": nomina.lote,
            "cantidad_declarada": nomina.cantidad,
            "suma_declarada": nomina.suma,
            "registros_en_detalle": len(nomina.registros),
            "resumen_esperado": resumen,
        }
        if incluir_registros:
            entrada["registros"] = [r.para_manifiesto() for r in nomina.registros]
    return entrada


def casos_de_cruce(gen: Generador, registros: list[Registro]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Cuentas de Banco Genérico para los registros válidos, con algunos casos que no calzan."""
    cuentas = [{"rut_titular": r.rut, "cuenta": r.cuenta, "codigo_banco": r.banco, "estado_cuenta": "Activa"}
               for r in registros]
    elegidos = gen.rng.sample(range(len(registros)), 13)
    casos = []
    for posicion, indice in enumerate(elegidos):
        registro, cuenta = registros[indice], cuentas[indice]
        if posicion < 5:
            cuenta["estado_cuenta"] = "Cerrada"
            caso = "Cuenta de destino cerrada"
        elif posicion < 10:
            cuenta["cuenta"] = ""  # se elimina al final: la cuenta no existe en el banco
            caso = "Cuenta de destino inexistente en Banco Genérico"
        else:
            cuenta["rut_titular"] = gen.rut()
            caso = "La cuenta pertenece a otro RUT"
        casos.append({"id_transaccion": registro.id_transaccion, "rut_deudor": registro.rut,
                      "cuenta_destino": registro.cuenta, "caso": caso, "resultado_sugerido": "Rechazado Banco"})
    cuentas = [c for c in cuentas if c["cuenta"]]
    gen.rng.shuffle(cuentas)
    return cuentas, casos


def generar(salida: Path, semilla: int = 2026, grande: int = 0) -> dict[str, object]:
    """Escribe todos los archivos simulados en `salida` y devuelve el manifiesto."""
    gen = Generador(semilla)
    estructurados = salida / "estructurados"
    no_estructurados = salida / "no_estructurados"
    banco = salida / "banco_generico"
    for carpeta in (estructurados, no_estructurados, banco):
        carpeta.mkdir(parents=True, exist_ok=True)

    archivos: list[dict[str, object]] = []
    para_cruce: list[Registro] = []

    def ruta(carpeta: Path, nombre: str) -> tuple[Path, str]:
        destino = carpeta / nombre
        return destino, destino.relative_to(salida).as_posix()

    # Formatos estructurados válidos
    destino, relativa = ruta(estructurados, "01_nomina_valida.xlsx")
    nomina = gen.nomina(150)
    escribir_excel(destino, nomina)
    archivos.append(entrada_manifiesto(relativa, "Excel", "Nómina válida en Excel, con celdas numéricas y de fecha.",
                                       "Procesado", nomina))
    para_cruce += nomina.registros
    nomina_excel = relativa

    destino, relativa = ruta(estructurados, "02_nomina_valida.csv")
    nomina_csv = gen.nomina(120)
    escribir_delimitado(destino, nomina_csv)
    archivos.append(entrada_manifiesto(relativa, "CSV", "Nómina válida en CSV UTF-8 separado por punto y coma.",
                                       "Procesado", nomina_csv))
    para_cruce += nomina_csv.registros

    destino, relativa = ruta(estructurados, "03_nomina_latin1.txt")
    nomina = gen.nomina(80)
    escribir_delimitado(destino, nomina, delimitador="|", encoding="latin-1")
    archivos.append(entrada_manifiesto(relativa, "TXT", "Nómina válida en TXT ISO-8859-1 separado por | (RN04 "
                                       "acepta UTF-8 e ISO-8859-1).", "Procesado", nomina))
    para_cruce += nomina.registros

    # Casos de borde por registro
    destino, relativa = ruta(estructurados, "04_nomina_casos_borde.xlsx")
    nomina = Nomina(gen.lote(), casos_de_borde(gen))
    escribir_excel(destino, nomina)
    archivos.append(entrada_manifiesto(
        relativa, "Excel", "Un caso por regla de validación (RN01-RN03, RF03). La suma declarada considera solo "
        "los montos numéricos del detalle.", "Procesado", nomina))

    destino, relativa = ruta(estructurados, "05_nomina_lote2_con_duplicados.csv")
    repetidos = [copia(r, estado=DUPLICADO, caso="Transacción ya enviada en 02_nomina_valida.csv",
                       motivo="RN02 - Ya procesada en otro archivo")
                 for r in gen.rng.sample(nomina_csv.registros, 5)]
    nomina = Nomina(gen.lote(), gen.registros(55) + repetidos)
    gen.rng.shuffle(nomina.registros)
    escribir_delimitado(destino, nomina)
    archivos.append(entrada_manifiesto(
        relativa, "CSV", "Segundo lote que repite 5 transacciones de 02. Los duplicados solo se detectan si 02 "
        "se procesó antes.", "Procesado", nomina))

    # Errores a nivel de archivo (RN04 y CU03 3a)
    destino, relativa = ruta(estructurados, "06_nomina_totales_no_cuadran.csv")
    nomina = gen.nomina(40)
    nomina.suma_declarada = nomina.suma + 125_000
    escribir_delimitado(destino, nomina)
    archivos.append(entrada_manifiesto(relativa, "CSV", "La suma del pie no coincide con el detalle.", "Error", nomina,
                                       motivo="CU03 3a - La suma declarada supera al detalle en $ 125.000"))

    destino, relativa = ruta(estructurados, "07_nomina_cantidad_no_cuadra.xlsx")
    nomina = gen.nomina(40)
    nomina.cantidad_declarada = 43
    escribir_excel(destino, nomina)
    archivos.append(entrada_manifiesto(relativa, "Excel", "El encabezado y el pie declaran 43 registros; el "
                                       "detalle tiene 40.", "Error", nomina,
                                       motivo="CU03 3a - Cantidad declarada distinta del detalle"))

    destino, relativa = ruta(estructurados, "08_nomina_sin_pie.csv")
    nomina = gen.nomina(30)
    escribir_delimitado(destino, nomina, con_pie=False)
    archivos.append(entrada_manifiesto(relativa, "CSV", "Falta la línea TOTALES al final.", "Error", nomina,
                                       motivo="RN04 - Estructura de encabezado y pie incompleta"))

    destino, relativa = ruta(estructurados, "09_nomina_columnas_incorrectas.csv")
    nomina = gen.nomina(30)
    columnas = tuple(c for c in COLUMNAS if c != "cuenta_destino")
    escribir_delimitado(destino, nomina, columnas=columnas, titulos={"monto": "importe"})
    archivos.append(entrada_manifiesto(relativa, "CSV", "Falta la columna cuenta_destino y monto se llama importe.",
                                       "Error", nomina, motivo="RN04 - Columnas distintas de la plantilla"))

    destino, relativa = ruta(estructurados, "10_nomina_corrupta.xlsx")
    destino.write_bytes(b"PK\x03\x04" + gen.rng.randbytes(2048))
    archivos.append(entrada_manifiesto(relativa, "Excel", "Bytes aleatorios con extensión .xlsx.", "Error",
                                       motivo="RN04 - Archivo corrupto"))

    destino, relativa = ruta(estructurados, "11_nomina_vacia.csv")
    nomina = Nomina(gen.lote(), [])
    escribir_delimitado(destino, nomina)
    archivos.append(entrada_manifiesto(relativa, "CSV", "Encabezado y pie correctos, sin registros.", "Por definir",
                                       nomina, motivo="El ERS no define qué hacer con una nómina sin registros"))

    destino, relativa = ruta(estructurados, "12_nomina_valida_reenvio.xlsx")
    shutil.copyfile(salida / nomina_excel, destino)
    archivos.append(entrada_manifiesto(relativa, "Excel", "Copia exacta de 01 con otro nombre.",
                                       "Rechazado (no se registra)",
                                       motivo="RN02 / CU02 4a - Archivo ya procesado (mismo contenido que 01)"))

    # Documentos no estructurados (RF12, RN05)
    destino, relativa = ruta(no_estructurados, "21_nomina_pdf_texto.pdf")
    nomina = gen.nomina(25)
    escribir_pdf_texto(destino, nomina)
    archivos.append(entrada_manifiesto(relativa, "PDF con texto", "Tabla con texto seleccionable: se extrae sin OCR.",
                                       "Procesado", nomina))
    para_cruce += nomina.registros

    destino, relativa = ruta(no_estructurados, "22_nomina_pdf_texto_totales_no_cuadran.pdf")
    nomina = gen.nomina(25)
    nomina.suma_declarada = nomina.suma - 50_000
    escribir_pdf_texto(destino, nomina)
    archivos.append(entrada_manifiesto(relativa, "PDF con texto", "El total impreso no coincide con la tabla.",
                                       "Error de Extracción", nomina,
                                       motivo="CU12 5b - Totales no cuadran: el documento va a revisión manual"))

    destino, relativa = ruta(no_estructurados, "23_nomina_escaneada.pdf")
    nomina = gen.nomina(25)
    escribir_pdf_escaneado(destino, nomina)
    archivos.append(entrada_manifiesto(
        relativa, "PDF escaneado", "Solo imagen, buena calidad. Leyendo celda por celda, Tesseract obtiene todos los "
        "montos con confianza de 90% o más; con OCR de página completa las líneas de la tabla hacen que se salte "
        "filas.", "Procesado", nomina))
    para_cruce += nomina.registros

    destino, relativa = ruta(no_estructurados, "24_foto_nomina.jpg")
    nomina = gen.nomina(25)
    manchadas = [4, 11, 19]
    for fila in manchadas:
        registro = nomina.registros[fila]
        registro.estado, registro.motivo = REVISION, "RN05 - Mancha sobre el monto: confianza OCR bajo 90%"
        registro.caso = "Monto tapado por una mancha"
    escribir_fotografia(destino, nomina, manchadas)
    archivos.append(entrada_manifiesto(
        relativa, "Imagen", "Foto con perspectiva, sombra y desenfoque. Los 3 montos manchados deben ir a revisión, "
        "y ningún valor mal leído puede aceptarse sin revisión; el resto depende de la calidad real del OCR.",
        "Error de Extracción", nomina,
        motivo="CU12 5b - Los montos manchados no se pueden leer, así que el detalle no cuadra con los totales: "
               "el documento va a revisión manual con los registros dudosos marcados"))
    para_cruce += [r for r in nomina.registros if r.estado == VALIDO]

    if grande:
        destino, relativa = ruta(estructurados, "90_nomina_volumen.csv")
        nomina = gen.nomina(grande)
        escribir_delimitado(destino, nomina)
        archivos.append(entrada_manifiesto(relativa, "CSV", f"Nómina válida de {grande} registros para pruebas de "
                                           "rendimiento.", "Procesado", nomina, incluir_registros=False))

    # Base simulada de Banco Genérico para el cruce (RF04)
    destino, relativa = ruta(banco, "cuentas_core_bancario.csv")
    cuentas, casos = casos_de_cruce(gen, para_cruce)
    escribir_cuentas_banco(destino, cuentas)

    manifiesto = {
        "descripcion": "Resultados esperados de los datos simulados de TTDH Automation. Generado por "
                       "backend/scripts/generar_datos_simulados.py; no editar a mano.",
        "semilla": semilla,
        "plantilla": {
            "encabezado": ["ENCABEZADO", "TGR", "<lote>", "<fecha AAAA-MM-DD>", "<cantidad de registros>"],
            "columnas": list(COLUMNAS),
            "pie": ["TOTALES", "<cantidad de registros>", "<suma de montos>"],
            "tipos_movimiento": list(TIPOS_MOVIMIENTO),
        },
        "archivos": archivos,
        "cruce_banco_generico": {
            "archivo": relativa,
            "cuentas": len(cuentas),
            "nota": "Los registros válidos de 01, 02, 03, 21, 23 y 24 tienen cuenta Activa, salvo estos casos. "
                    "El resultado es una sugerencia: la regla de cruce la define el equipo.",
            "casos": casos,
        },
    }
    (salida / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    return manifiesto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera las nóminas TGR simuladas de TTDH Automation.")
    parser.add_argument("--salida", type=Path, default=CARPETA_SALIDA,
                        help=f"carpeta de destino (por defecto {CARPETA_SALIDA})")
    parser.add_argument("--semilla", type=int, default=2026, help="semilla aleatoria (por defecto 2026)")
    parser.add_argument("--grande", type=int, default=0, metavar="N",
                        help="agrega una nómina CSV válida de N registros para pruebas de volumen")
    args = parser.parse_args(argv)
    if args.grande < 0:
        parser.error("--grande debe ser 0 o mayor")

    salida = args.salida.resolve()
    print(f"Generando datos simulados en {salida}")
    manifiesto = generar(salida, args.semilla, args.grande)
    for archivo in manifiesto["archivos"]:
        resumen = archivo.get("resumen_esperado")
        detalle = ", ".join(f"{estado}: {n}" for estado, n in resumen.items()) if resumen else "-"
        print(f"  {archivo['archivo']:<60} {archivo['estado_archivo_esperado']:<27} {detalle}")
    cruce = manifiesto["cruce_banco_generico"]
    print(f"  {cruce['archivo']:<60} {cruce['cuentas']} cuentas, {len(cruce['casos'])} casos de cruce")
    print(f"Listo: {len(manifiesto['archivos'])} nóminas y manifiesto.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
