"""Preparación de fotografías de nóminas para el OCR (RF12, etapa 3).

Una foto de celular trae perspectiva, fondo alrededor de la hoja, sombras y menos resolución
que un escaneo. Aquí se deja como si fuera un escaneo y luego se procesa igual que uno (ocr.py).
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .ocr import extraer_de_imagenes
from .plantilla import ResultadoExtraccion

ANCHO_OBJETIVO = 2339  # px: una hoja A4 apaisada a 200 dpi, la resolución de los escaneos
AREA_MINIMA_HOJA = 0.3  # fracción de la foto que debe ocupar la hoja para considerarla detectada
# Margen que se conserva alrededor de lo detectado, como fracción de su tamaño: arriba va el
# encabezado (lote, fecha) y abajo los totales.
MARGEN_LADOS, MARGEN_ARRIBA, MARGEN_ABAJO = 0.03, 0.22, 0.10


def cargar_imagen(ruta: Path) -> np.ndarray:
    """Imagen en escala de grises, girada según la orientación EXIF del celular.

    Se usa Pillow porque cv2.imread no abre rutas con tildes en Windows.
    """
    with Image.open(ruta) as imagen:
        return np.array(ImageOps.exif_transpose(imagen).convert("L"))


def _ordenar_esquinas(puntos: np.ndarray) -> np.ndarray:
    """Superior izquierda, superior derecha, inferior derecha, inferior izquierda."""
    suma, resta = puntos.sum(axis=1), np.diff(puntos, axis=1).ravel()
    return np.array([puntos[suma.argmin()], puntos[resta.argmin()], puntos[suma.argmax()], puntos[resta.argmax()]],
                    dtype=np.float32)


def enderezar_hoja(gris: np.ndarray) -> np.ndarray:
    """Detecta la hoja contra el fondo y corrige la perspectiva.

    Si no encuentra una hoja (por ejemplo, la foto ya viene recortada), solo la lleva a la
    resolución de trabajo.
    """
    alto, ancho = gris.shape
    # Se busca el borde de la hoja y no su brillo: con sombra, parte del papel queda tan oscura
    # como el fondo y un umbral la recortaría.
    bordes = cv2.Canny(cv2.GaussianBlur(gris, (5, 5), 0), 30, 90)
    bordes = cv2.dilate(bordes, np.ones((5, 5), np.uint8))
    contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contorno = max((cv2.convexHull(c) for c in contornos), key=cv2.contourArea, default=None)
    area = cv2.contourArea(contorno) if contorno is not None else 0
    if not AREA_MINIMA_HOJA * alto * ancho <= area <= 0.98 * alto * ancho:
        return cv2.resize(gris, None, fx=ANCHO_OBJETIVO / ancho, fy=ANCHO_OBJETIVO / ancho,
                          interpolation=cv2.INTER_CUBIC)

    aproximado = cv2.approxPolyDP(contorno, 0.02 * cv2.arcLength(contorno, True), True)
    puntos = aproximado.reshape(-1, 2) if len(aproximado) == 4 else cv2.boxPoints(cv2.minAreaRect(contorno))
    esquinas = _ordenar_esquinas(puntos.astype(np.float32))
    sup_izq, sup_der, inf_der, inf_izq = esquinas
    ancho_hoja = max(np.linalg.norm(sup_der - sup_izq), np.linalg.norm(inf_der - inf_izq))
    alto_hoja = max(np.linalg.norm(inf_izq - sup_izq), np.linalg.norm(inf_der - sup_der))
    # Lo más marcado suele ser el borde de la tabla, no el de la hoja. Se endereza con esas esquinas
    # pero dejando margen: la corrección vale para todo el plano del papel, así que el encabezado y
    # los totales, que están fuera de la tabla, también quedan derechos.
    ancho_tabla = ANCHO_OBJETIVO
    alto_tabla = round(alto_hoja * ANCHO_OBJETIVO / ancho_hoja)
    izquierda, arriba, abajo = round(ancho_tabla * MARGEN_LADOS), round(alto_tabla * MARGEN_ARRIBA), \
        round(alto_tabla * MARGEN_ABAJO)
    destino = np.array([[izquierda, arriba], [izquierda + ancho_tabla, arriba],
                        [izquierda + ancho_tabla, arriba + alto_tabla], [izquierda, arriba + alto_tabla]],
                       dtype=np.float32)
    matriz = cv2.getPerspectiveTransform(esquinas, destino)
    tamano = (ancho_tabla + 2 * izquierda, arriba + alto_tabla + abajo)
    return cv2.warpPerspective(gris, matriz, tamano, flags=cv2.INTER_CUBIC, borderValue=255)


def quitar_sombra(gris: np.ndarray) -> np.ndarray:
    """Divide por una estimación del fondo del papel para emparejar la iluminación."""
    fondo = cv2.medianBlur(cv2.dilate(gris, np.ones((7, 7), np.uint8)), 51)
    return cv2.divide(gris, fondo, scale=255)


def preparar_foto(ruta: Path) -> np.ndarray:
    return quitar_sombra(enderezar_hoja(cargar_imagen(ruta)))


def extraer_foto(ruta: Path) -> ResultadoExtraccion:
    return extraer_de_imagenes([preparar_foto(ruta)], "Imagen")
