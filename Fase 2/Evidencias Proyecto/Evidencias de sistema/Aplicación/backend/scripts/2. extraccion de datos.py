"""Extrae 15 campos de resoluciones TGR ficticias a un CSV para ETL.

Uso: python extraer_datos_tgr.py
Dependencia: pip install pymupdf
Solo trabaja con datos presentes en PDF (no inventa fechas de correo).
"""
from pathlib import Path
from datetime import datetime
import csv
import re
import unicodedata

try:
    import fitz
except ImportError as exc:
    raise SystemExit('Falta PyMuPDF. Instala con: pip install pymupdf') from exc

CARPETA_PDF = Path(__file__).resolve().parent / 'documentos_generados'
ARCHIVO_CSV = CARPETA_PDF / 'extraccion_tgr.csv'
DELIMITADOR = ';'

COLUMNAS = [
    'NOMBRE DOCUMENTO', 'RUT', 'DV', 'ID DEMANDA', 'N RESOLUCION',
    'FECHA GESTION', 'NOMBRE CLIENTE', 'MONTO SOLICITADO', 'ROL',
    'FECHA INGRESO CASILLA', 'TESORERIA', 'FECHA OFICIO',
    'MULTIPLES ROLES', 'REVISION MANUAL', 'CAMPOS FALTANTES OCR',
]

# Estos campos no aparecen necesariamente en el oficio, por lo que quedan
# pendientes para revisión o integración con los metadatos de correo.
OBLIGATORIOS = COLUMNAS[1:12]
MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
}
DIAS = {'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4,
        'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8,
        'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
        'trece': 13, 'catorce': 14, 'quince': 15,
        'dieciseis': 16, 'diecisiete': 17, 'dieciocho': 18,
        'diecinueve': 19, 'veinte': 20, 'veintiuno': 21,
        'veintidos': 22, 'veintitres': 23, 'veinticuatro': 24,
        'veinticinco': 25, 'veintiseis': 26, 'veintisiete': 27,
        'veintiocho': 28, 'veintinueve': 29, 'treinta': 30,
        'treinta y uno': 31}


def normalizar(cadena):
    return ''.join(c for c in unicodedata.normalize('NFD', cadena)
                   if unicodedata.category(c) != 'Mn')


def primera(patron, texto, flags=re.I):
    match = re.search(patron, texto, flags)
    return match.group(1).strip() if match else ''


def unicos(valores):
    return list(dict.fromkeys(x.strip() for x in valores if x.strip()))


def fecha_oficio(texto):
    # La fecha impresa en página de firma tiene prioridad.
    fechas = re.findall(r'\bFecha\s*:\s*(\d{2}[/-]\d{2}[/-]\d{4})', texto, re.I)
    if fechas:
        return fechas[-1].replace('/', '-')
    # Alternativa: fecha expresada en palabras en primera página.
    t = normalizar(texto.lower())
    patron = r'\ba\s+([a-z ]+?)\s+de\s+([a-z]+)\s+de\s+(\d{4})\b'
    m = re.search(patron, t)
    if m:
        dia = DIAS.get(m.group(1).strip())
        mes = MESES.get(m.group(2).strip())
        if dia and mes:
            return f'{dia:02d}-{mes:02d}-{int(m.group(3)):04d}'
    return ''


def procesar_pdf(ruta):
    fila = dict.fromkeys(COLUMNAS, '')
    fila['NOMBRE DOCUMENTO'] = ruta.name
    try:
        with fitz.open(ruta) as doc:
            texto = '\n'.join(page.get_text(sort=True) for page in doc)
    except Exception:
        fila['MULTIPLES ROLES'] = 'NO'
        fila['REVISION MANUAL'] = 'SI'
        fila['CAMPOS FALTANTES OCR'] = 'NO SE PUDO LEER EL PDF'
        return fila

    rut = re.search(r'\bRUT\s*:\s*([\d.]{7,12})\s*-\s*([\dKk])\b', texto, re.I)
    if rut:
        fila['RUT'] = rut.group(1).replace('.', '')
        fila['DV'] = rut.group(2).upper()
    # El nombre se encuentra inmediatamente antes del RUT.
    cliente = re.search(r'\n\s*([^\n]+?)\s*,\s*RUT\s*:', texto, re.I)
    if cliente:
        fila['NOMBRE CLIENTE'] = cliente.group(1).strip()

    demandas = unicos(re.findall(r'\bID\s*DEMANDA\s*:\s*(\d{5,})', texto, re.I))
    roles = unicos(re.findall(r'\bExpediente\s+Administrativo\s+Rol\s*N\s*[°ºo]?\s*([\d-]+)', texto, re.I))
    resoluciones = unicos(re.findall(r'\bRESOLUCI[OÓ]N\s*N\s*[°ºo]?\s*(\d{5,})', texto, re.I))

    fila['ID DEMANDA'] = ' | '.join(demandas)
    fila['ROL'] = ' | '.join(roles)
    fila['N RESOLUCION'] = ' | '.join(resoluciones)

    # Se interpreta MULTIPLES ROLES como más de un ROL o ID DEMANDA
    # distinto detectado en el documento.
    fila['MULTIPLES ROLES'] = 'SI' if len(demandas) > 1 or len(roles) > 1 else 'NO'

    monto = primera(r'\$\s*([\d.]+)\s*,\s*correspondiente\s+a\s+la\s+deuda', texto)
    if not monto:
        monto = primera(r'\$\s*([\d.]+)', texto)
    fila['MONTO SOLICITADO'] = monto.replace('.', '')

    fila['TESORERIA'] = primera(r'TESORER[IÍ]A\s+REGIONAL\s+DE\s+([^\n|]+)', texto)
    if not fila['TESORERIA']:
        fila['TESORERIA'] = primera(r'DIRECTOR\s+REGIONAL\s+TESORERO\s+DE\s+([^\n]+)', texto)
    fila['FECHA OFICIO'] = fecha_oficio(texto)

    # No se deduce la fecha de gestión ni la recepción del correo de
    # la fecha de firma: son eventos distintos.
    faltantes = [campo for campo in OBLIGATORIOS if not fila[campo]]
    fila['REVISION MANUAL'] = 'SI' if faltantes else 'NO'
    fila['CAMPOS FALTANTES OCR'] = ' | '.join(faltantes) if faltantes else ''
    return fila


def main():
    rutas = sorted(CARPETA_PDF.glob('*.pdf'))
    if not rutas:
        raise SystemExit(f'No se encontraron archivos PDF en {CARPETA_PDF}')
    filas = [procesar_pdf(ruta) for ruta in rutas]
    with ARCHIVO_CSV.open('w', encoding='utf-8-sig', newline='') as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS, delimiter=DELIMITADOR)
        escritor.writeheader()
        escritor.writerows(filas)
    print(f'PDF procesados: {len(filas)}')
    print(f'Revisión manual requerida: {sum(f["REVISION MANUAL"] == "SI" for f in filas)}')
    print(f'CSV generado: {ARCHIVO_CSV}')


if __name__ == '__main__':
    main()
