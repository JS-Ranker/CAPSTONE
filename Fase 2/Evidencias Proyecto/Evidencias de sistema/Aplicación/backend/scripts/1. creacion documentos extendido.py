from pathlib import Path
from datetime import datetime, timedelta
import random
import csv

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF


# ============================================================
# CONFIGURACIÓN
# ============================================================

CANTIDAD_DOCUMENTOS = 100

ANIO = 2026

RUTA_SALIDA = (
    Path(__file__).resolve().parent
    / "documentos_generados"
)

RUTA_SALIDA.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# DATOS FALSOS
# ============================================================

LOCALIDADES = [
    "TALCA", "CURICO", "LINARES", "CAUQUENES", "CONSTITUCION",
    "PARRAL", "SAN JAVIER", "MOLINA", "TENO", "ROMERAL",
    "SAGRADA FAMILIA", "RAUCO", "HUALANE", "LICANTEN", "VICHUQUEN",
    "CUREPTO", "PELARCO", "PENCAHUE", "SAN CLEMENTE", "MAULE",
    "SAN RAFAEL", "RIO CLARO", "COLBUN", "YERBAS BUENAS",
    "LONGAVI", "RETIRO", "VILLA ALEGRE", "CHANCO", "PELLUHUE",
    "EMPEDRADO",
]

# Se conservan los nombres originales y se agregan combinaciones
# para crear miles de clientes ficticios diferentes.
NOMBRES_ORIGINALES = [
    "JUAN CARLOS PEREZ GONZALEZ",
    "MARIA FERNANDA ROJAS SILVA",
    "PEDRO ANTONIO MUÑOZ CONTRERAS",
    "COMERCIAL PRUEBA LIMITADA",
    "SERVICIOS INDUSTRIALES DEL MAULE SPA",
    "INVERSIONES EJEMPLO SPA",
    "TRANSPORTES CLIENTE PRUEBA LIMITADA",
    "SOCIEDAD DEMOSTRACION SPA",
]

NOMBRES_PERSONA = [
    "JUAN", "PEDRO", "DIEGO", "MARTIN", "NICOLAS", "MATIAS",
    "SEBASTIAN", "FRANCISCO", "FELIPE", "BENJAMIN", "TOMAS",
    "VICENTE", "JOSE", "CARLOS", "ANDRES", "IGNACIO", "PABLO",
    "CRISTOBAL", "GABRIEL", "MAURICIO", "RODRIGO", "DANIEL",
    "FERNANDO", "EDUARDO", "RICARDO", "JAVIER", "LUIS", "HUGO",
    "MARIA", "ANA", "CAMILA", "SOFIA", "VALENTINA", "CATALINA",
    "FERNANDA", "JAVIERA", "PAULA", "CAROLINA", "DANIELA",
    "CONSTANZA", "ANTONIA", "ISIDORA", "FRANCISCA", "MACARENA",
    "PATRICIA", "ANDREA", "ISABEL", "LORENA", "NATALIA", "ELENA",
]

SEGUNDOS_NOMBRES = [
    "", "", "", "ANDRES", "ANTONIO", "IGNACIO", "ALBERTO",
    "ALEJANDRO", "EDUARDO", "JAVIER", "MANUEL", "SEBASTIAN",
    "JOSE", "FERNANDA", "PAZ", "ELIZABETH", "ALEJANDRA",
    "BEATRIZ", "BELEN", "SOFIA", "CAROLINA", "ISABEL",
]

APELLIDOS = [
    "GONZALEZ", "MUÑOZ", "ROJAS", "DIAZ", "PEREZ", "SOTO",
    "CONTRERAS", "SILVA", "MARTINEZ", "SEPULVEDA", "MORALES",
    "RODRIGUEZ", "LOPEZ", "FUENTES", "HERNANDEZ", "TORRES",
    "ARAYA", "FLORES", "ESPINOZA", "VALENZUELA", "CASTILLO",
    "RAMIREZ", "REYES", "GUTIERREZ", "CASTRO", "VARGAS",
    "ALVAREZ", "VASQUEZ", "TAPIA", "FERNANDEZ", "SANCHEZ",
    "CARRASCO", "GOMEZ", "CORTES", "NUÑEZ", "SALAZAR",
    "HERRERA", "AGUILERA", "FARIAS", "LEIVA", "MIRANDA",
    "BRAVO", "VERGARA", "CAMPOS", "PIZARRO", "OYARZUN",
]

RUBROS_EMPRESAS = [
    "COMERCIAL", "INVERSIONES", "TRANSPORTES", "SERVICIOS",
    "CONSTRUCTORA", "DISTRIBUIDORA", "AGRICOLA", "TECNOLOGIA",
    "LOGISTICA", "ASESORIAS", "IMPORTADORA", "EXPORTADORA",
    "INDUSTRIAL", "MANTENCIONES", "CONSULTORA", "SOLUCIONES",
]

NOMBRES_EMPRESAS = [
    "DEL MAULE", "LOS ROBLES", "SAN MIGUEL", "VALLE CENTRAL",
    "NUEVA ERA", "LA UNION", "LOS ANDES", "RIO CLARO",
    "EL PROGRESO", "SANTA ELENA", "LOS AROMOS", "LAS PALMAS",
    "VALLE VERDE", "HORIZONTE", "CENTRO SUR", "EL BOSQUE",
    "LA ESTRELLA", "SUR ANDINO", "NUEVO SIGLO", "ALTO SUR",
]

# Direcciones .invalid: se usan para evitar confundir los datos de
# prueba con correos de contacto reales.
CORREOS = {
    localidad: (
        "retenciones-" + localidad.lower().replace(" ", "-").replace("ñ", "n")
        + "@example.invalid"
    )
    for localidad in LOCALIDADES
}


def generar_nombre_cliente():
    """Genera personas y empresas ficticias con alta variabilidad."""
    if random.random() < 0.12:
        if random.random() < 0.15:
            return random.choice(NOMBRES_ORIGINALES)
        return (
            f"{random.choice(RUBROS_EMPRESAS)} "
            f"{random.choice(NOMBRES_EMPRESAS)} "
            f"{random.choice(['SPA', 'LIMITADA'])}"
        )
    nombre = random.choice(NOMBRES_PERSONA)
    segundo = random.choice(SEGUNDOS_NOMBRES)
    apellidos = random.sample(APELLIDOS, 2)
    return " ".join(parte for parte in (nombre, segundo, *apellidos) if parte)


MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


DIAS_TEXTO = {
    1: "uno",
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
    11: "once",
    12: "doce",
    13: "trece",
    14: "catorce",
    15: "quince",
    16: "dieciséis",
    17: "diecisiete",
    18: "dieciocho",
    19: "diecinueve",
    20: "veinte",
    21: "veintiuno",
    22: "veintidós",
    23: "veintitrés",
    24: "veinticuatro",
    25: "veinticinco",
    26: "veintiséis",
    27: "veintisiete",
    28: "veintiocho",
    29: "veintinueve",
    30: "treinta",
    31: "treinta y uno",
}


# ============================================================
# FUNCIONES GENERALES
# ============================================================

def calcular_dv_rut(numero):
    suma = 0
    multiplicador = 2

    for digito in reversed(str(numero)):
        suma += int(digito) * multiplicador

        multiplicador += 1

        if multiplicador > 7:
            multiplicador = 2

    resto = 11 - (suma % 11)

    if resto == 11:
        return "0"

    if resto == 10:
        return "K"

    return str(resto)


def generar_rut():
    numero = random.randint(
        7_000_000,
        25_000_000
    )

    dv = calcular_dv_rut(numero)

    return numero, dv


def formatear_rut(numero, dv):
    cuerpo = f"{numero:,}".replace(",", ".")

    return f"{cuerpo}-{dv}"


def formatear_monto(valor):
    return f"{valor:,}".replace(",", ".")


def generar_fecha():
    inicio = datetime(
        ANIO,
        1,
        1
    )

    fin = datetime(
        ANIO,
        12,
        31
    )

    dias = (
        fin - inicio
    ).days

    return inicio + timedelta(
        days=random.randint(
            0,
            dias
        )
    )


def fecha_texto(fecha, localidad):

    dia = DIAS_TEXTO[
        fecha.day
    ]

    mes = MESES[
        fecha.month - 1
    ]

    return (
        f"En {localidad.title()}, "
        f"a {dia} de {mes} "
        f"de {ANIO}"
    )


def generar_datos():

    fecha = generar_fecha()

    localidad = random.choice(
        LOCALIDADES
    )

    rut_numero, rut_dv = generar_rut()

    datos = {

        "codigo_documento":
            f"E{random.randint(100000, 999999)}/{ANIO}",

        "localidad":
            localidad,

        "fecha":
            fecha,

        "nombre": generar_nombre_cliente(),

        "nombre_autoridad": random.choice([
            "LUIS ALBERTO MORALES SOTO",
            "CAROLINA ANDREA REYES SILVA",
            "MARCELA PATRICIA ARAYA LOPEZ",
            "JORGE IGNACIO CASTILLO PEREZ",
            "CLAUDIA FERNANDA DIAZ ROJAS",
            "RODRIGO MANUEL FUENTES TORRES",
        ]),

        "rut_numero":
            rut_numero,

        "rut_dv":
            rut_dv,

        "rut":
            formatear_rut(
                rut_numero,
                rut_dv
            ),

        "rol":
            (
                f"{random.randint(10000, 99999)}"
                f"-{ANIO}"
            ),

        "monto":
            random.randint(
                500_000,
                25_000_000
            ),

        "id_demanda":
            random.randint(
                10_000_000,
                99_999_999
            ),

        "resolucion":
            random.randint(
                1_000_000,
                99_999_999
            ),

        "correo":
            CORREOS[
                localidad
            ],

        "codigo_barra":
            str(
                random.randint(
                    100000000,
                    999999999
                )
            ),

    }

    return datos


# ============================================================
# DIBUJO LOGO SIMULADO
# ============================================================

def dibujar_logo_tgr(pdf, ancho, alto):

    x = ancho - 62 * mm
    y = alto - 28 * mm

    pdf.setFont(
        "Helvetica-Bold",
        15
    )

    pdf.drawString(
        x,
        y,
        "TGR"
    )

    pdf.setFont(
        "Helvetica",
        6
    )

    pdf.drawString(
        x,
        y - 4 * mm,
        "Tesorería General"
    )

    pdf.drawString(
        x,
        y - 7 * mm,
        "de la República"
    )

    pdf.setFont(
        "Helvetica-Bold",
        7
    )

    pdf.drawString(
        x + 24 * mm,
        y + 1 * mm,
        "Recaudamos"
    )

    pdf.drawString(
        x + 24 * mm,
        y - 3 * mm,
        "equidad"
    )

    pdf.drawString(
        x + 24 * mm,
        y - 7 * mm,
        "y desarrollo"
    )

    pdf.drawString(
        x + 24 * mm,
        y - 11 * mm,
        "para Chile"
    )


# ============================================================
# PÁGINA 1
# ============================================================

def dibujar_pagina_1(
    pdf,
    datos
):

    ancho, alto = A4

    # Código superior derecho

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawRightString(
        ancho - 15 * mm,
        alto - 10 * mm,
        datos["codigo_documento"]
    )

    # Logo

    dibujar_logo_tgr(
        pdf,
        ancho,
        alto
    )

    # Fecha/lugar

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        12 * mm,
        alto - 48 * mm,
        fecha_texto(
            datos["fecha"],
            datos["localidad"]
        )
    )

    # VISTOS Y CONSIDERANDO

    y = alto - 65 * mm

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        25 * mm,
        y,
        "VISTOS Y CONSIDERANDO:"
    )

    y -= 8 * mm

    pdf.setFont(
        "Helvetica",
        9
    )

    texto_1 = (
        f"1.    Que, en Expediente Administrativo Rol N° "
        f"{datos['rol']} de {datos['localidad']}, se sigue ejecución "
        f"en contra de"
    )

    pdf.drawString(
        28 * mm,
        y,
        texto_1
    )

    y -= 6 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            f"{datos['nombre']}, "
            f"RUT: {datos['rut']}."
        )
    )

    y -= 10 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            "2.    Que, no habiéndose embargado bienes de su propiedad "
            "o aquellos embargados resultan insuficientes"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        (
            "para garantizar el pago del total adeudado "
            "o resultan de difícil realización."
        )
    )

    y -= 10 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            "3.    Que, la deuda demandada se encuentra impaga "
            "y el cobro no está sujeto a suspensión alguna."
        )
    )

    y -= 10 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            "4.    Que, se ha tomado conocimiento que el deudor/a "
            "mantiene productos bancarios y financieros en"
        )
    )

    y -= 6 * mm

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        35 * mm,
        y,
        "BANCO ESTADO."
    )

    y -= 10 * mm

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        28 * mm,
        y,
        (
            "5.    Lo dispuesto en el artículo 170, 171, 174 y 195 "
            "del Código Tributario y lo dispuesto en el artículo 456"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        "del Código de Procedimiento Civil;"
    )

    # RESUELVO

    y -= 16 * mm

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        25 * mm,
        y,
        "RESUELVO:"
    )

    y -= 10 * mm

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        28 * mm,
        y,
        (
            "1.    Reténgase todos los fondos en productos bancarios "
            "y financieros disponibles que se encuentren en"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        (
            "la entidad financiera indicada de propiedad del/la "
            "deudor/a antes individualizado/a, en lo que exceda"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        (
            "al monto de 50% de 1 UTM y hasta el monto de "
            f"$ {formatear_monto(datos['monto'])}, "
            "correspondiente a la deuda demandada"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        (
            "en autos más reajustes, intereses y multas."
        )
    )

    y -= 10 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            "2.    Notifíquese la presente resolución "
            "a la entidad financiera."
        )
    )

    y -= 10 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            "3.    Remítase a la Tesorería General de la República, "
            "RUT 60.805.000-0, conforme al protocolo acordado,"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        (
            "bajo apercibimiento de que, si no diere cumplimiento "
            "a la retención y remisión de los fondos"
        )
    )

    y -= 6 * mm

    pdf.drawString(
        35 * mm,
        y,
        (
            "embargados, quedará solidariamente responsable "
            "del pago de las sumas que haya dejado de retener."
        )
    )

    y -= 10 * mm

    pdf.drawString(
        28 * mm,
        y,
        (
            "4.    Notifíquese la presente resolución al ejecutado."
        )
    )

    # Marca discreta prueba

    pdf.setFont(
        "Helvetica",
        5
    )

    pdf.drawString(
        8 * mm,
        8 * mm,
        "DOCUMENTO FICTICIO GENERADO PARA PRUEBAS"
    )


# ============================================================
# PÁGINA 2
# ============================================================

def dibujar_pagina_2(
    pdf,
    datos
):

    ancho, alto = A4

    y = alto - 28 * mm

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        25 * mm,
        y,
        (
            "Resolvió el Sr. JUEZ SUSTANCIADOR Y "
            f"DIRECTOR REGIONAL TESORERO DE {datos['localidad']}"
        )
    )

    # Tabla Datos de Contacto

    y -= 18 * mm

    x = 25 * mm

    ancho_total = 160 * mm
    alto_fila = 11 * mm

    pdf.rect(
        x,
        y,
        ancho_total,
        alto_fila
    )

    pdf.line(
        x + 32 * mm,
        y,
        x + 32 * mm,
        y + alto_fila
    )

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        x + 2 * mm,
        y + 4 * mm,
        "Datos de Contacto"
    )

    pdf.setFont(
        "Helvetica-Bold",
        8
    )

    pdf.drawString(
        x + 35 * mm,
        y + 4 * mm,
        datos["correo"]
    )

    # ID DEMANDA

    y -= 14 * mm

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        x,
        y,
        f"ID DEMANDA: {datos['id_demanda']}"
    )

    # Resolución

    y -= 7 * mm

    pdf.drawString(
        x,
        y,
        f"RESOLUCIÓN N° {datos['resolucion']}"
    )

    # Línea institucional

    y -= 35 * mm

    pdf.setLineWidth(
        0.5
    )

    pdf.line(
        42 * mm,
        y,
        ancho - 18 * mm,
        y
    )

    pdf.setFont(
        "Helvetica",
        6
    )

    pdf.drawRightString(
        ancho - 18 * mm,
        y - 5 * mm,
        (
            f"Tesorería Regional de {datos['localidad'].title()} "
            "| Sección Unidades de Cobro"
        )
    )

    # Pie inferior

    pdf.setFont(
        "Helvetica-Bold",
        5
    )

    pdf.drawString(
        5 * mm,
        13 * mm,
        (
            "RESOLUCIÓN COBRANZA "
            f"(E) N° {datos['resolucion']}"
        )
    )

    pdf.setFont(
        "Helvetica",
        5
    )



# ============================================================
# QR SIMULADO
# ============================================================

def dibujar_qr_simulado(
    pdf,
    x,
    y,
    tamano=22 * mm
):

    random.seed(
        random.randint(
            1,
            999999
        )
    )

    celdas = 21

    lado = tamano / celdas

    for fila in range(celdas):

        for columna in range(celdas):

            if random.random() > 0.50:

                pdf.rect(
                    x + columna * lado,
                    y + fila * lado,
                    lado,
                    lado,
                    fill=1,
                    stroke=0
                )


# ============================================================
# PÁGINA 3
# ============================================================

def dibujar_pagina_3(
    pdf,
    datos
):

    ancho, alto = A4

    # código arriba derecha

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawRightString(
        ancho - 15 * mm,
        alto - 10 * mm,
        datos["codigo_documento"]
    )

    # Firma / autoridad

    centro_x = ancho / 2

    y = 113 * mm

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawCentredString(
        centro_x,
        y,
        datos["nombre_autoridad"]
    )

    y -= 5 * mm

    pdf.drawCentredString(
        centro_x,
        y,
        "DIRECTOR(A) REGIONAL"
    )

    y -= 5 * mm

    pdf.drawCentredString(
        centro_x,
        y,
        "TESORERO"
    )

    y -= 5 * mm

    pdf.drawCentredString(
        centro_x,
        y,
        (
            f"TESORERÍA REGIONAL DE "
            f"{datos['localidad']}"
        )
    )

    y -= 5 * mm

    pdf.drawCentredString(
        centro_x,
        y,
        (
            f"Fecha: "
            f"{datos['fecha'].strftime('%d/%m/%Y')}"
        )
    )

    # Iniciales

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        20 * mm,
        75 * mm,
        "LSP / mtr"
    )

    # Distribución

    pdf.setFont(
        "Helvetica-Bold",
        7
    )

    pdf.drawString(
        20 * mm,
        60 * mm,
        "Distribución:"
    )

    # Línea

    pdf.line(
        20 * mm,
        52 * mm,
        ancho - 20 * mm,
        52 * mm
    )

    # QR simulado

    dibujar_qr_simulado(
        pdf,
        25 * mm,
        20 * mm,
        22 * mm
    )

    # Texto validación

    pdf.setFont(
        "Helvetica",
        7
    )

    pdf.drawString(
        52 * mm,
        45 * mm,
        (
            "Para verificar la validez de este documento puede escanear"
        )
    )

    pdf.drawString(
        52 * mm,
        40 * mm,
        (
            "el código QR desde su dispositivo móvil o ingresar al"
        )
    )

    pdf.drawString(
        52 * mm,
        35 * mm,
        (
            "sitio web correspondiente e ingresar el código de barra."
        )
    )

    pdf.drawString(
        52 * mm,
        30 * mm,
        (
            "Documento generado exclusivamente para pruebas."
        )
    )

    # Código de barras

    barcode = code128.Code128(
        datos["codigo_barra"],
        barHeight=12 * mm,
        barWidth=0.35
    )

    barcode.drawOn(
        pdf,
        145 * mm,
        27 * mm
    )

    pdf.setFont(
        "Helvetica",
        5
    )

    pdf.drawCentredString(
        166 * mm,
        24 * mm,
        datos["codigo_barra"]
    )

    pdf.drawString(
        8 * mm,
        7 * mm,
        "DOCUMENTO FICTICIO GENERADO PARA PRUEBAS"
    )


# ============================================================
# GENERAR PDF
# ============================================================

def crear_pdf(
    datos,
    numero_documento
):

    nombre_archivo = (
        f"TGR_PRUEBA_"
        f"{numero_documento:04d}.pdf"
    )

    ruta_pdf = (
        RUTA_SALIDA
        / nombre_archivo
    )

    pdf = canvas.Canvas(
        str(ruta_pdf),
        pagesize=A4
    )

    pdf.setTitle(
        nombre_archivo
    )

    # Página 1

    dibujar_pagina_1(
        pdf,
        datos
    )

    pdf.showPage()

    # Página 2

    dibujar_pagina_2(
        pdf,
        datos
    )

    # Firma, QR y validacion en la segunda pagina (sin pagina vacia extra)

    dibujar_pagina_3(
        pdf,
        datos
    )

    pdf.showPage()

    pdf.save()

    return ruta_pdf


# ============================================================
# MAIN
# ============================================================

def main():

    # Los RUT no se repiten dentro de una misma ejecución.
    ruts_utilizados = set()
    registros_clientes = []

    print()
    print("=" * 60)
    print("GENERADOR DOCUMENTOS TGR DE PRUEBA")
    print("=" * 60)

    for numero in range(
        1,
        CANTIDAD_DOCUMENTOS + 1
    ):

        datos = generar_datos()
        while datos["rut_numero"] in ruts_utilizados:
            datos = generar_datos()
        ruts_utilizados.add(datos["rut_numero"])

        registros_clientes.append({
            "archivo_pdf": f"TGR_PRUEBA_{numero:04d}.pdf",
            "rut": datos["rut_numero"],
            "dv": datos["rut_dv"],
            "nombre_cliente": datos["nombre"],
            "localidad": datos["localidad"],
            "monto": datos["monto"],
            "codigo_documento": datos["codigo_documento"],
        })

        ruta_pdf = crear_pdf(
            datos,
            numero
        )

        print(
            f"[{numero:03d}] "
            f"{ruta_pdf.name}"
        )

    ruta_csv = RUTA_SALIDA / "clientes_tgr.csv"
    with ruta_csv.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=[
            "archivo_pdf", "rut", "dv", "nombre_cliente",
            "localidad", "monto", "codigo_documento",
        ], delimiter=";")
        escritor.writeheader()
        escritor.writerows(registros_clientes)

    print(f"Listado CSV de clientes: {ruta_csv.name}")
    print()
    print(
        f"Documentos generados: "
        f"{CANTIDAD_DOCUMENTOS}"
    )

    print(
        f"Carpeta: "
        f"{RUTA_SALIDA}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()