"""OCR local con Tesseract de nóminas en imagen: PDF escaneados y fotografías (RF12, RN05).

Pasos por página:
1. Enderezar la imagen usando las líneas horizontales de la tabla.
2. Detectar la grilla (líneas horizontales y verticales).
3. Borrar las líneas y leer la tabla completa de una vez. Con las líneas, Tesseract se salta
   filas enteras; leer celda por celda es exacto pero lento (unas 225 llamadas por página).
4. Ubicar cada palabra en su celda según su posición.
5. Volver a leer por separado, agrandadas, solo las celdas críticas poco confiables.

No se restringen los caracteres (tessedit_char_whitelist): con Tesseract 5, la lectura sale
correcta pero con confianza 0, lo que mandaría todo a revisión.
"""
import functools
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pdfplumber
import pytesseract

from app.config import settings

from .documento import columna_desde_titulo, leer_encabezado_y_totales
from .normalizacion import normalizar, rut_valido
from .plantilla import CAMPOS_CRITICOS, COLUMNAS_PLANTILLA, UMBRAL_CONFIANZA, RegistroExtraido, ResultadoExtraccion

RESOLUCION_DPI = 200
IDIOMA = "spa"
ANGULO_MAXIMO = 5.0  # grados; un giro mayor no se corrige (probablemente no es una tabla)
# Se releen si quedan bajo el umbral: los críticos de RN05 y los que forman la clave de RN02.
CAMPOS_RELECTURA = (*CAMPOS_CRITICOS, "id_transaccion", "fecha_origen")
# Interpretación de RN05 acordada por el equipo: Tesseract suele dar 80-89% a RUT bien leídos
# (sobre todo con K). Si el RUT leído pasa Módulo 11, un error de lectura es muy improbable
# (1 en 11), así que con al menos esta confianza se considera confiable.
CONFIANZA_MINIMA_RUT_VERIFICADO = 80.0


@dataclass
class Celda:
    texto: str
    confianza: float  # 0-100; 100 en una celda vacía sin tinta


@dataclass
class Grilla:
    filas_y: list[int]  # posición de cada línea horizontal
    columnas_x: list[int]  # posición de cada línea vertical

    def fila_de(self, y: float) -> int | None:
        return _intervalo(self.filas_y, y)

    def columna_de(self, x: float) -> int | None:
        return _intervalo(self.columnas_x, x)

    def interior(self, fila: int, columna: int, margen: int = 3) -> tuple[slice, slice]:
        return (slice(self.filas_y[fila] + margen, self.filas_y[fila + 1] - margen),
                slice(self.columnas_x[columna] + margen, self.columnas_x[columna + 1] - margen))


def _intervalo(bordes: list[int], valor: float) -> int | None:
    indice = bisect_right(bordes, valor) - 1
    return indice if 0 <= indice < len(bordes) - 1 else None


@functools.cache
def _configurar_tesseract() -> None:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    try:
        idiomas = pytesseract.get_languages()
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError(f"No se encontró Tesseract en {settings.tesseract_cmd!r}: "
                           "revisa TESSERACT_CMD en backend/.env.") from error
    if IDIOMA not in idiomas:
        raise RuntimeError(f"Tesseract no tiene instalado el idioma {IDIOMA!r} (español).")


def paginas_pdf(ruta: Path) -> list[np.ndarray]:
    """Páginas de un PDF como imágenes en escala de grises."""
    with pdfplumber.open(ruta) as pdf:
        return [np.array(p.to_image(resolution=RESOLUCION_DPI).original.convert("L")) for p in pdf.pages]


def _binarizar(gris: np.ndarray) -> np.ndarray:
    """Tinta en blanco sobre fondo negro, tolerante a sombras y fondos irregulares."""
    return cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)


def _lineas(binaria: np.ndarray, horizontales: bool, largo: int) -> np.ndarray:
    forma = (largo, 1) if horizontales else (1, largo)
    return cv2.morphologyEx(binaria, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, forma))


def _posiciones(perfil: np.ndarray, minimo: float) -> list[int]:
    """Centro de cada grupo de filas/columnas del perfil que supera el mínimo."""
    indices = np.flatnonzero(perfil > minimo)
    if indices.size == 0:
        return []
    grupos = np.split(indices, np.flatnonzero(np.diff(indices) > 5) + 1)
    return [int(grupo.mean()) for grupo in grupos]


def enderezar(gris: np.ndarray) -> np.ndarray:
    alto, ancho = gris.shape
    # Segmentos cortos para que una línea inclinada no se pierda al buscar horizontales.
    horizontales = _lineas(_binarizar(gris), True, ancho // 40)
    lineas = cv2.HoughLinesP(horizontales, 1, np.pi / 1800, 200, minLineLength=ancho // 4, maxLineGap=20)
    if lineas is None:
        return gris
    angulo = float(np.median([np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in lineas.reshape(-1, 4)]))
    if abs(angulo) < 0.05 or abs(angulo) > ANGULO_MAXIMO:
        return gris
    matriz = cv2.getRotationMatrix2D((ancho / 2, alto / 2), angulo, 1.0)
    return cv2.warpAffine(gris, matriz, (ancho, alto), flags=cv2.INTER_CUBIC, borderValue=255)


def detectar_grilla(gris: np.ndarray) -> Grilla | None:
    alto, ancho = gris.shape
    binaria = _binarizar(gris)
    filas_y = _posiciones(_lineas(binaria, True, ancho // 15).sum(axis=1) / 255, ancho * 0.3)
    if len(filas_y) < 3:
        return None
    alto_tabla = filas_y[-1] - filas_y[0]
    columnas_x = _posiciones(_lineas(binaria, False, alto // 30).sum(axis=0) / 255, alto_tabla * 0.5)
    if len(columnas_x) < 3:
        return None
    return Grilla(filas_y, columnas_x)


def _celda(palabras: list[tuple[str, float]], tiene_tinta: bool) -> Celda:
    # Los tokens sin letras ni dígitos ("|", "_", "$") suelen ser restos de líneas o manchas, y
    # Tesseract les da confianza baja: contarlos arrastraría la confianza de toda la celda.
    palabras = [(texto, conf) for texto, conf in palabras if any(c.isalnum() for c in texto)]
    if palabras:
        return Celda(" ".join(texto for texto, _ in palabras), min(conf for _, conf in palabras))
    return Celda("", 0.0 if tiene_tinta else 100.0)


def _palabras(imagen: np.ndarray, config: str) -> list[tuple[str, float, float, float]]:
    """(texto, confianza, centro x, centro y) de cada palabra que reconoce Tesseract."""
    datos = pytesseract.image_to_data(imagen, lang=IDIOMA, config=config, output_type=pytesseract.Output.DICT)
    return [(texto, float(conf), izq + ancho / 2, arriba + alto / 2)
            for texto, conf, izq, arriba, ancho, alto
            in zip(datos["text"], datos["conf"], datos["left"], datos["top"], datos["width"], datos["height"])
            if texto.strip()]


def leer_celdas(gris: np.ndarray, grilla: Grilla) -> tuple[list[list[Celda]], np.ndarray]:
    """Lee toda la tabla y devuelve las celdas por fila, más la imagen sin líneas."""
    alto, ancho = gris.shape
    binaria = _binarizar(gris)
    lineas = cv2.dilate(_lineas(binaria, True, ancho // 15) | _lineas(binaria, False, alto // 30),
                        np.ones((3, 3), np.uint8))
    sin_lineas = gris.copy()
    sin_lineas[lineas > 0] = 255
    tinta = binaria & ~lineas

    y0, x0 = grilla.filas_y[0], grilla.columnas_x[0]
    tabla = sin_lineas[y0:grilla.filas_y[-1], x0:grilla.columnas_x[-1]]
    por_celda: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for texto, conf, x, y in _palabras(tabla, "--psm 6"):
        fila, columna = grilla.fila_de(y + y0), grilla.columna_de(x + x0)
        if fila is not None and columna is not None:
            por_celda.setdefault((fila, columna), []).append((texto, conf))

    filas = []
    for fila in range(len(grilla.filas_y) - 1):
        celdas = []
        for columna in range(len(grilla.columnas_x) - 1):
            tiene_tinta = tinta[grilla.interior(fila, columna)].mean() > 255 * 0.01
            celdas.append(_celda(por_celda.get((fila, columna), []), tiene_tinta))
        filas.append(celdas)
    return filas, sin_lineas


def releer(sin_lineas: np.ndarray, grilla: Grilla, fila: int, columna: int) -> Celda:
    """Lee una sola celda, agrandada al doble (Tesseract rinde mejor con letras más grandes)."""
    recorte = cv2.resize(sin_lineas[grilla.interior(fila, columna)], None, fx=2, fy=2,
                         interpolation=cv2.INTER_CUBIC)
    recorte = cv2.copyMakeBorder(recorte, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    palabras = _palabras(recorte, "--psm 7")
    return _celda([(texto, conf) for texto, conf, _, _ in palabras], tiene_tinta=True)


def _registro(celdas: list[Celda], columnas: list[str | None], fila: int,
              sin_lineas: np.ndarray, grilla: Grilla) -> RegistroExtraido:
    valores, confianzas = {}, {}
    for indice, (columna, celda) in enumerate(zip(columnas, celdas)):
        if columna is None:
            continue
        if columna in CAMPOS_RELECTURA and celda.confianza < UMBRAL_CONFIANZA:
            releida = releer(sin_lineas, grilla, fila, indice)
            if releida.confianza > celda.confianza:
                celda = releida
        valor, confianza = normalizar(columna, celda.texto), celda.confianza
        if columna == "rut_deudor" and confianza >= CONFIANZA_MINIMA_RUT_VERIFICADO and rut_valido(valor):
            confianza = max(confianza, UMBRAL_CONFIANZA)
        valores[columna], confianzas[columna] = valor, confianza
    return RegistroExtraido(valores, confianzas)


def _texto(region: np.ndarray) -> str:
    if region.shape[0] < 20:
        return ""
    return pytesseract.image_to_string(region, lang=IDIOMA, config="--psm 6")


def extraer_de_imagenes(paginas: list[np.ndarray], tipo_documento: str) -> ResultadoExtraccion:
    _configurar_tesseract()
    resultado = ResultadoExtraccion(tipo_documento=tipo_documento)
    textos_fuera_de_tabla = []
    columnas: list[str | None] | None = None

    for numero, pagina in enumerate(paginas, start=1):
        gris = enderezar(pagina)
        grilla = detectar_grilla(gris)
        if grilla is None:
            resultado.observaciones.append(f"Página {numero}: no se detectó una tabla.")
            textos_fuera_de_tabla.append(_texto(gris))
            continue
        textos_fuera_de_tabla += [_texto(gris[:grilla.filas_y[0]]), _texto(gris[grilla.filas_y[-1]:])]
        filas, sin_lineas = leer_celdas(gris, grilla)
        for fila, celdas in enumerate(filas):
            posibles = [columna_desde_titulo(celda.texto, tolerante=True) for celda in celdas]
            if set(COLUMNAS_PLANTILLA) <= set(posibles):  # fila de títulos
                columnas = posibles
                continue
            vacia = all(celda.texto == "" and celda.confianza == 100.0 for celda in celdas)
            if columnas is not None and not vacia:
                resultado.registros.append(_registro(celdas, columnas, fila, sin_lineas, grilla))

    leer_encabezado_y_totales(resultado, "\n".join(textos_fuera_de_tabla))
    if columnas is None:
        resultado.errores.append("No se encontró una tabla con las columnas de la plantilla estándar.")
        return resultado
    resultado.verificar_totales()
    return resultado


def extraer_escaneado(ruta: Path) -> ResultadoExtraccion:
    return extraer_de_imagenes(paginas_pdf(ruta), "PDF escaneado")
