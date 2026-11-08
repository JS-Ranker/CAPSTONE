"""Genera los documentos simulados de la TGR para desarrollar y probar TTDH Automation.

El documento real es la resolución de retención de la TGR: un deudor por documento, en dos páginas. Su diseño lo
da "1. creacion documentos extendido.py" (de David); este script lo usa como base y arma las variantes que el
sistema debe poder leer: PDF con texto, PDF escaneado, fotografía (JPG), captura (PNG), Word, TXT, Excel y CSV,
con casos válidos y casos con problemas (dato faltante, RUT inválido, reenvío repetido, anomalía, archivo
corrupto o vacío). También escribe una base simulada de cuentas de Banco Genérico y un manifiesto con el
resultado esperado de cada archivo, que sirve de referencia para las pruebas.

Uso, desde la carpeta backend/:
    python scripts/generar_datos_simulados.py                  # escribe en ../data/simulados
    python scripts/generar_datos_simulados.py --salida otra    # otra carpeta

Con la misma semilla el resultado es siempre el mismo. Solo se sobrescriben los archivos que genera este script;
nunca se borra nada de la carpeta de salida.

Los RUT se generan entre 40.000.000 y 49.999.999, fuera de los rangos que hoy se asignan a personas (bajo 30
millones) y empresas (desde 50 millones), para no asociar por accidente a una persona real con una deuda.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pdfplumber
from docx import Document
from openpyxl import Workbook
from PIL import Image

CARPETA_SALIDA = Path(__file__).resolve().parents[2] / "data" / "simulados"
SCRIPT_BASE = Path(__file__).with_name("1. creacion documentos extendido.py")

COLUMNAS_PLANTILLA = ("rut", "nombre", "id_demanda", "n_resolucion", "monto_solicitado", "tipo_embargo",
                      "expediente", "tesoreria", "fecha_oficio")
ROTULOS = {  # cómo se titula cada dato en los Excel y CSV de una resolución
    "rut": "RUT", "nombre": "Nombre", "id_demanda": "ID demanda", "n_resolucion": "N° resolución",
    "monto_solicitado": "Monto solicitado", "tipo_embargo": "Tipo embargo", "expediente": "Expediente",
    "tesoreria": "Tesorería", "fecha_oficio": "Fecha oficio",
}
DPI = 200
CODIGO_BANCO_GENERICO = "099"
TIPOS_CUENTA = ("Cuenta RUT", "Cuenta corriente", "Chequera electrónica", "Cuenta de ahorro")
MEDIA_UTM_REFERENCIA = 35_000  # 0,5 UTM aproximada (la UTM real la ingresa el analista en la aplicación)
FECHA_FIJA = datetime(2026, 1, 1)

SIN_MONTO = ("hasta el monto de $ {monto}, correspondiente a la deuda demandada",
             "hasta el monto de la deuda demandada")


def _cargar_base():
    spec = importlib.util.spec_from_file_location("resoluciones_tgr", SCRIPT_BASE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@dataclass
class Deudor:
    datos: dict
    banco: str = ""  # escenario del core bancario (ver cuentas_banco)

    @property
    def rut_con_dv(self) -> str:
        return f"{self.datos['rut_numero']}-{self.datos['rut_dv']}"

    def esperado(self, **cambios: str) -> dict[str, str]:
        d = self.datos
        localidad = d["localidad"].upper()
        valores = {
            "rut": self.rut_con_dv, "nombre": d["nombre"], "id_demanda": str(d["id_demanda"]),
            "n_resolucion": str(d["resolucion"]), "monto_solicitado": str(d["monto"]), "tipo_embargo": "RETENCIÓN",
            "expediente": f"{d['rol']} {localidad}", "tesoreria": f"TESORERÍA REGIONAL DE {localidad}",
            "fecha_oficio": d["fecha"].date().isoformat(),
        }
        valores.update(cambios)
        return valores


class Generador:
    def __init__(self, salida: Path, semilla: int):
        self.salida = salida
        self.semilla = semilla
        self.rng = random.Random(semilla)
        random.seed(semilla)  # el script base usa el generador global
        self.base = _cargar_base()
        self.ruts: set[int] = set()
        self.numero = 0
        self.archivos: list[dict] = []
        for carpeta in ("estructurados", "no_estructurados", "banco_generico"):
            (salida / carpeta).mkdir(parents=True, exist_ok=True)

    # --- deudores y PDF base -------------------------------------------------------------------------
    def deudor(self, banco: str = "", monto: int | None = None) -> Deudor:
        datos = self.base.generar_datos()
        while True:
            numero = self.rng.randint(40_000_000, 49_999_999)
            if numero not in self.ruts:
                self.ruts.add(numero)
                break
        datos["rut_numero"], datos["rut_dv"] = numero, self.base.calcular_dv_rut(numero)
        datos["rut"] = self.base.formatear_rut(numero, datos["rut_dv"])
        datos["fecha"] = FECHA_FIJA + timedelta(days=self.rng.randint(10, 300))
        if monto is not None:
            datos["monto"] = monto
        return Deudor(datos, banco)

    def pdf(self, deudor: Deudor, destino: Path) -> Path:
        self.numero += 1
        with tempfile.TemporaryDirectory() as carpeta:
            self.base.RUTA_SALIDA = Path(carpeta)
            origen = self.base.crear_pdf(deudor.datos, self.numero)
            shutil.copyfile(origen, destino)
        return destino

    @staticmethod
    def texto(pdf: Path) -> str:
        with pdfplumber.open(pdf) as doc:
            return "\n".join((pagina.extract_text() or "") for pagina in doc.pages)

    @staticmethod
    def paginas(pdf: Path) -> list[Image.Image]:
        with pdfplumber.open(pdf) as doc:
            return [pagina.to_image(resolution=DPI).original.convert("RGB") for pagina in doc.pages]

    # --- variantes de texto, tabla de pares, imagen ---------------------------------------------------
    def pares(self, deudor: Deudor, sin: tuple[str, ...] = (), rut: str | None = None) -> list[list[str]]:
        valores = deudor.esperado()
        d = deudor.datos
        valores["rut"] = rut or d["rut"]
        valores["monto_solicitado"] = d["monto"]  # número, como lo escribe un sistema
        valores["fecha_oficio"] = d["fecha"].strftime("%d-%m-%Y")
        filas = [["Resolución de retención de la TGR (documento ficticio)", ""], ["Código documento", d["codigo_documento"]]]
        filas += [[ROTULOS[c], valores[c]] for c in COLUMNAS_PLANTILLA if c not in sin]
        return filas

    def escribir_excel(self, destino: Path, filas: list[list]) -> None:
        libro = Workbook()
        libro.properties.created = libro.properties.modified = FECHA_FIJA
        hoja = libro.active
        hoja.title = "Resolución"
        for fila in filas:
            hoja.append(fila)
        hoja.column_dimensions["A"].width = 24
        hoja.column_dimensions["B"].width = 40
        libro.save(destino)

    @staticmethod
    def escribir_csv(destino: Path, filas: list[list]) -> None:
        with destino.open("w", encoding="utf-8-sig", newline="") as archivo:
            csv.writer(archivo, delimiter=";").writerows(filas)

    @staticmethod
    def escribir_word(destino: Path, texto: str) -> None:
        documento = Document()
        documento.core_properties.created = documento.core_properties.modified = FECHA_FIJA
        for linea in texto.splitlines():
            if linea.strip():
                documento.add_paragraph(linea.strip())
        documento.save(destino)

    @staticmethod
    def escaneo(imagen: Image.Image, rng: random.Random, grados: float, ruido: float, desenfoque: float) -> Image.Image:
        gris = np.array(imagen.convert("L"), dtype=np.float32)
        alto, ancho = gris.shape
        giro = cv2.getRotationMatrix2D((ancho / 2, alto / 2), grados, 1.0)
        gris = cv2.warpAffine(gris, giro, (ancho, alto), flags=cv2.INTER_CUBIC, borderValue=250)
        if desenfoque:
            gris = cv2.GaussianBlur(gris, (0, 0), desenfoque)
        gris += np.random.default_rng(rng.randint(0, 10**6)).normal(0, ruido, gris.shape)
        return Image.fromarray(np.clip(gris * 0.97 + 4, 0, 255).astype(np.uint8)).convert("RGB")

    @staticmethod
    def apilar(paginas: list[Image.Image], separacion: int = 40) -> Image.Image:
        ancho = max(p.width for p in paginas)
        alto = sum(p.height for p in paginas) + separacion * (len(paginas) - 1)
        hoja = Image.new("RGB", (ancho, alto), (255, 255, 255))
        y = 0
        for pagina in paginas:
            hoja.paste(pagina, (0, y))
            y += pagina.height + separacion
        return hoja

    @staticmethod
    def fotografia(hoja: Image.Image, rng: random.Random, inclinacion: int, sombra: float, desenfoque: float) -> Image.Image:
        """La hoja sobre una mesa, vista con perspectiva y sombra, como una foto de celular."""
        ancho_foto, alto_foto = 1900, 1900 * hoja.height // hoja.width + 500
        fuente = np.array(hoja.resize((1400, 1400 * hoja.height // hoja.width)))
        h, w = fuente.shape[:2]
        gen = np.random.default_rng(rng.randint(0, 10**6))
        fondo = np.full((alto_foto, ancho_foto, 3), (72, 62, 55), dtype=np.float32)
        fondo += gen.normal(0, 7, fondo.shape)
        origen = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        x0, y0 = 250, 230
        d = lambda: rng.randint(-inclinacion, inclinacion)  # noqa: E731
        destino = np.float32([[x0 + d(), y0 + d()], [x0 + w + d(), y0 + d()],
                              [x0 + w + d(), y0 + h + d()], [x0 + d(), y0 + h + d()]])
        matriz = cv2.getPerspectiveTransform(origen, destino)
        hoja_c = cv2.warpPerspective(fuente, matriz, (ancho_foto, alto_foto), flags=cv2.INTER_LINEAR)
        mascara = cv2.warpPerspective(np.full((h, w), 255, np.uint8), matriz, (ancho_foto, alto_foto))
        gradiente = np.linspace(1.0 - sombra, 1.0, ancho_foto, dtype=np.float32)[None, :, None]
        foto = np.where(mascara[..., None] > 0, hoja_c.astype(np.float32) * gradiente, fondo)
        if desenfoque:
            foto = cv2.GaussianBlur(foto, (0, 0), desenfoque)
        return Image.fromarray(np.clip(foto, 0, 255).astype(np.uint8))

    # --- registro del manifiesto -----------------------------------------------------------------------
    def anotar(self, ruta: Path, formato: str, descripcion: str, estado: str, deudor: Deudor | None,
               valores: dict[str, str] | None = None, revision: bool | None = False, duplicado_de: str | None = None,
               ocr: bool = False) -> None:
        self.archivos.append({
            "archivo": ruta.relative_to(self.salida).as_posix(), "formato": formato, "descripcion": descripcion,
            "estado_extraccion_esperado": estado,
            "requiere_revision_esperada": revision if estado == "Normalizado" else None,
            "lee_con_ocr": ocr,
            "duplicado_de": duplicado_de,
            "deudor": (valores if valores is not None else deudor.esperado()) if deudor and estado == "Normalizado" else None,
            "escenario_banco": deudor.banco if deudor else None,
        })


def generar(salida: Path, semilla: int = 2026) -> dict[str, object]:
    """Escribe todos los documentos simulados en `salida` y devuelve el manifiesto."""
    g = Generador(salida, semilla)
    est, no_est = salida / "estructurados", salida / "no_estructurados"
    deudores: list[Deudor] = []

    def nuevo(banco: str = "", monto: int | None = None) -> Deudor:
        d = g.deudor(banco, monto)
        deudores.append(d)
        return d

    # --- PDF con texto: el documento de David tal cual ----------------------------------------------------
    d1, d2 = nuevo("cubre"), nuevo("parcial")
    pdf1 = g.pdf(d1, no_est / "01_resolucion_pdf_texto.pdf")
    g.anotar(pdf1, "PDF con texto", "Resolución válida en PDF con texto (la base de todas las demás).",
             "Normalizado", d1)
    pdf2 = g.pdf(d2, no_est / "02_resolucion_pdf_texto_otra_tesoreria.pdf")
    g.anotar(pdf2, "PDF con texto", "Otro deudor, otra tesorería regional y otro monto.", "Normalizado", d2)
    reenvio = no_est / "03_resolucion_pdf_texto_reenvio.pdf"
    shutil.copyfile(pdf1, reenvio)
    g.anotar(reenvio, "PDF con texto", "Reenvío idéntico del archivo 01: la recepción lo rechaza como duplicado.",
             "Normalizado", d1, duplicado_de=g.archivos[0]["archivo"])
    anomalo = nuevo("cubre", monto=480_000_000)
    g.anotar(g.pdf(anomalo, no_est / "04_resolucion_pdf_texto_monto_anomalo.pdf"), "PDF con texto",
             "Monto muy sobre lo habitual (480 millones): la IA lo marca como anomalía.", "Normalizado", anomalo)
    corrupto = no_est / "05_resolucion_pdf_corrupto.pdf"
    corrupto.write_bytes(b"%PDF-1.4\n% archivo danado a proposito\n" + bytes(range(256)) * 4)
    g.anotar(corrupto, "PDF con texto", "PDF dañado: no se puede abrir; va a revisión manual del documento.",
             "Error de Extracción", None)

    # --- PDF escaneado, fotografía y captura ----------------------------------------------------------------
    d3, d4 = nuevo("cubre"), nuevo("sin_cuentas")
    for deudor, nombre, grados, ruido, desenfoque, descripcion in (
            (d3, "06_resolucion_escaneada.pdf", 0.4, 3.0, 0.0, "Escaneo limpio, apenas girado."),
            (d4, "07_resolucion_escaneada_con_ruido.pdf", -0.9, 9.0, 0.7, "Escaneo con ruido y giro mayor.")):
        origen = g.pdf(deudor, Path(tempfile.gettempdir()) / f"_ttdh_{nombre}")
        rng = random.Random(g.rng.randint(0, 10**6))
        hojas = [g.escaneo(p, rng, grados, ruido, desenfoque) for p in g.paginas(origen)]
        destino = no_est / nombre
        hojas[0].save(destino, "PDF", resolution=DPI, save_all=True, append_images=hojas[1:])
        origen.unlink()
        g.anotar(destino, "PDF escaneado", descripcion, "Normalizado", deudor, revision=False, ocr=True)

    d5, d6 = nuevo("cubre"), nuevo("sobre_media_utm")
    for deudor, nombre, inclinacion, sombra, desenfoque, calidad, descripcion in (
            (d5, "08_resolucion_foto.jpg", 25, 0.10, 0.6, 88, "Foto de celular de las dos hojas, con perspectiva."),
            (d6, "09_resolucion_foto_con_sombra.jpg", 55, 0.35, 1.1, 70, "Foto con más inclinación y sombra.")):
        origen = g.pdf(deudor, Path(tempfile.gettempdir()) / f"_ttdh_{nombre}.pdf")
        rng = random.Random(g.rng.randint(0, 10**6))
        foto = g.fotografia(g.apilar(g.paginas(origen)), rng, inclinacion, sombra, desenfoque)
        origen.unlink()
        destino = no_est / nombre
        foto.save(destino, "JPEG", quality=calidad)
        g.anotar(destino, "Imagen", descripcion, "Normalizado", deudor, revision=False, ocr=True)

    d7, d8 = nuevo("parcial"), nuevo("cubre")
    for deudor, nombre, escala, descripcion in (
            (d7, "10_resolucion_captura.png", 1.0, "Captura de pantalla de las dos hojas, nítida."),
            (d8, "11_resolucion_captura_baja_resolucion.png", 0.42,
             "Captura reducida a poco más de 80 dpi: el OCR duda y el documento va a revisión.")):
        origen = g.pdf(deudor, Path(tempfile.gettempdir()) / f"_ttdh_{nombre}.pdf")
        imagen = g.apilar(g.paginas(origen))
        origen.unlink()
        if escala != 1.0:
            imagen = imagen.resize((round(imagen.width * escala), round(imagen.height * escala)), Image.BILINEAR)
        destino = no_est / nombre
        imagen.save(destino, "PNG")
        g.anotar(destino, "Imagen", descripcion, "Normalizado", deudor, revision=escala < 0.5, ocr=True)

    # --- Excel, CSV, TXT y Word ------------------------------------------------------------------------------
    d9, d10, d11, d12 = nuevo("cubre"), nuevo("parcial"), nuevo("cubre"), nuevo("cubre")
    base_texto = {}
    for deudor in (d11, d12):
        with tempfile.TemporaryDirectory() as carpeta:
            base_texto[deudor.rut_con_dv] = g.texto(g.pdf(deudor, Path(carpeta) / "base.pdf"))

    excel = est / "12_resolucion_valida.xlsx"
    g.escribir_excel(excel, g.pares(d9))
    g.anotar(excel, "Excel", "Resolución válida en Excel (filas campo / valor).", "Normalizado", d9)
    reenvio_excel = est / "13_resolucion_valida_reenvio.xlsx"
    shutil.copyfile(excel, reenvio_excel)
    g.anotar(reenvio_excel, "Excel", "Reenvío idéntico del archivo 12: se rechaza como duplicado.", "Normalizado", d9,
             duplicado_de=g.archivos[-1]["archivo"])
    csv_valido = est / "14_resolucion_valida.csv"
    g.escribir_csv(csv_valido, g.pares(d10))
    g.anotar(csv_valido, "CSV", "Resolución válida en CSV (campo;valor, UTF-8).", "Normalizado", d10)
    word = est / "15_resolucion_valida.docx"
    g.escribir_word(word, base_texto[d11.rut_con_dv])
    g.anotar(word, "Word", "Resolución válida en Word, con el mismo texto del PDF.", "Normalizado", d11)
    txt = est / "16_resolucion_latin1.txt"
    txt.write_bytes(base_texto[d12.rut_con_dv].encode("latin-1", errors="replace"))
    g.anotar(txt, "TXT", "Resolución en texto plano ISO-8859-1.", "Normalizado", d12)

    # --- casos con problemas ---------------------------------------------------------------------------------
    d13, d14, d15 = nuevo("cubre"), nuevo("cubre"), nuevo("cubre")
    sin_monto = est / "17_resolucion_sin_monto.xlsx"
    g.escribir_excel(sin_monto, g.pares(d13, sin=("monto_solicitado",)))
    g.anotar(sin_monto, "Excel", "Falta el monto solicitado: el ETL lo rechaza y queda en la Bandeja de Excepciones (RN05).", "Normalizado",
             d13, valores=d13.esperado(monto_solicitado=""), revision=True)
    with tempfile.TemporaryDirectory() as carpeta:
        texto = g.texto(g.pdf(d14, Path(carpeta) / "base.pdf"))
    antes, despues = SIN_MONTO[0].format(monto=f"{d14.datos['monto']:,}".replace(",", ".")), SIN_MONTO[1]
    assert antes in texto, "el texto de la resolución cambió: ajustar SIN_MONTO"
    sin_monto_txt = est / "18_resolucion_sin_monto.docx"
    g.escribir_word(sin_monto_txt, texto.replace(antes, despues))
    g.anotar(sin_monto_txt, "Word", "El texto no trae el monto: el ETL lo rechaza y queda en la Bandeja de Excepciones (RN05).", "Normalizado",
             d14, valores=d14.esperado(monto_solicitado=""), revision=True)
    rut_malo = f"{d15.datos['rut_numero']:,}".replace(",", ".") + "-" + ("0" if d15.datos["rut_dv"] != "0" else "1")
    rut_invalido = est / "19_resolucion_rut_invalido.csv"
    g.escribir_csv(rut_invalido, g.pares(d15, rut=rut_malo))
    g.anotar(rut_invalido, "CSV", "El dígito verificador del RUT no corresponde: el ETL lo rechaza (RN01).",
             "Normalizado", d15, valores=d15.esperado(rut=rut_malo.replace(".", "")), revision=False)
    deudores.remove(d15)  # no es cliente del banco: su RUT no existe

    xlsx_corrupto = est / "20_resolucion_corrupta.xlsx"
    xlsx_corrupto.write_bytes(b"PK\x03\x04 esto no es un Excel" + bytes(range(200)))
    g.anotar(xlsx_corrupto, "Excel", "Excel dañado: va a revisión manual del documento (RN04).", "Error de Extracción", None)
    vacio = est / "21_resolucion_vacia.csv"
    vacio.write_bytes(b"")
    g.anotar(vacio, "CSV", "Archivo vacío: va a revisión manual del documento.", "Error de Extracción", None)
    otro = est / "22_informe_otro_formato.csv"
    g.escribir_csv(otro, [["producto", "cantidad", "precio"], ["Tornillos", 100, 35], ["Tuercas", 100, 20]])
    g.anotar(otro, "CSV", "No es una resolución de la TGR: va a revisión manual del documento.",
             "Error de Extracción", None)

    # --- core bancario simulado -----------------------------------------------------------------------------
    cuentas = cuentas_banco(g, deudores)
    with (salida / "banco_generico" / "cuentas_core_bancario.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=["rut_titular", "cuenta", "codigo_banco", "tipo_cuenta", "saldo",
                                                       "estado_cuenta"], delimiter=";")
        escritor.writeheader()
        escritor.writerows(cuentas)

    manifiesto = {
        "descripcion": "Resultados esperados de las resoluciones simuladas de la TGR de TTDH Automation. Generado por "
                       "backend/scripts/generar_datos_simulados.py; no editar a mano.",
        "semilla": semilla,
        "columnas": list(COLUMNAS_PLANTILLA),
        "archivos": g.archivos,
        "banco_generico": {"archivo": "banco_generico/cuentas_core_bancario.csv", "cuentas": len(cuentas),
                           "escenarios": {"sin_cuentas": "el deudor no es cliente", "sobre_media_utm":
                                          "saldo total bajo 0,5 UTM: no se descuenta", "cubre":
                                          "el saldo alcanza para cubrir la deuda", "parcial":
                                          "el saldo cubre solo una parte de la deuda"}},
    }
    (salida / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    return manifiesto


def cuentas_banco(g: Generador, deudores: list[Deudor]) -> list[dict[str, str]]:
    """Cuentas de Banco Genérico de los deudores, con saldos que recorren la regla del cruce (RF04)."""
    cuentas: list[dict[str, str]] = []

    def cuenta(rut: str, saldo: int, estado: str = "Activa") -> None:
        cuentas.append({"rut_titular": rut, "cuenta": str(g.rng.randint(10**9, 10**10 - 1)),
                        "codigo_banco": CODIGO_BANCO_GENERICO, "tipo_cuenta": g.rng.choice(TIPOS_CUENTA),
                        "saldo": str(saldo), "estado_cuenta": estado})

    for deudor in deudores:
        deuda = deudor.datos["monto"]
        if deudor.banco == "sin_cuentas":
            continue
        if deudor.banco == "sobre_media_utm":
            saldo_total = g.rng.randint(0, MEDIA_UTM_REFERENCIA - 1)
        elif deudor.banco == "parcial":
            saldo_total = max(MEDIA_UTM_REFERENCIA, deuda * g.rng.randint(20, 90) // 100)
        else:
            saldo_total = deuda + g.rng.randint(1, 50) * 10_000
        partes = g.rng.randint(1, 3)
        cortes = sorted(g.rng.randint(0, saldo_total) for _ in range(partes - 1))
        for desde, hasta in zip([0, *cortes], [*cortes, saldo_total]):
            cuenta(deudor.rut_con_dv, hasta - desde)
        if g.rng.random() < 0.3:
            cuenta(deudor.rut_con_dv, g.rng.randint(100, 5_000) * 1_000, g.rng.choice(("Bloqueada", "Cerrada")))
    for _ in range(12):  # clientes del banco que no tienen deuda
        numero = g.rng.randint(40_000_000, 49_999_999)
        if numero not in g.ruts:
            cuenta(f"{numero}-{g.base.calcular_dv_rut(numero)}", g.rng.randint(0, 3_000) * 1_000)
    g.rng.shuffle(cuentas)
    return cuentas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera las resoluciones simuladas de la TGR de TTDH Automation.")
    parser.add_argument("--salida", type=Path, default=CARPETA_SALIDA,
                        help=f"carpeta de destino (por defecto {CARPETA_SALIDA})")
    parser.add_argument("--semilla", type=int, default=2026, help="semilla aleatoria (por defecto 2026)")
    args = parser.parse_args(argv)
    salida = args.salida.resolve()
    print(f"Generando documentos simulados en {salida}")
    manifiesto = generar(salida, args.semilla)
    for archivo in manifiesto["archivos"]:
        print(f"  {archivo['archivo']:<62} {archivo['estado_extraccion_esperado']}")
    banco = manifiesto["banco_generico"]
    print(f"  {banco['archivo']:<62} {banco['cuentas']} cuentas")
    print(f"Listo: {len(manifiesto['archivos'])} documentos y manifiesto.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
