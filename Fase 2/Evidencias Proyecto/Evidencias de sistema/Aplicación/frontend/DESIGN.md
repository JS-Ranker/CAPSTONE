---
name: TTDH Automation
description: Herramienta de trabajo diaria para procesar informes de la TGR, con la lógica de una oficina de partes y sus sellos de recepción.
colors:
  riel-azul-noche: "#16233f"
  riel-azul-noche-hover: "#0f1a31"
  tinta-de-timbre: "#3d3a9e"
  tinta-suave: "#ebedf6"
  verde-procesado: "#1f7a46"
  verde-procesado-fondo: "#edf6f0"
  ambar-pendiente: "#a35f00"
  ambar-pendiente-texto: "#7a4800"
  ambar-pendiente-fondo: "#fdf5e7"
  rojo-revision: "#b3261e"
  rojo-revision-fondo: "#fcf0ee"
  gris-frio-fondo: "#f5f6f8"
  papel: "#ffffff"
  papel-sutil: "#f8f9fb"
  papel-cabecera: "#eef0f5"
  regla-fina: "#dde1ea"
  regla-control: "#bfc6d4"
  regla-campo: "#7c8798"
  texto: "#16233f"
  texto-suave: "#55617a"
  texto-ejemplo: "#667189"
  riel-texto: "#c9d1e4"
  riel-texto-tenue: "#93a0be"
  riel-ok: "#4cc38a"
  riel-error: "#f06a5f"
  riel-error-texto: "#f6a49c"
  texto-deshabilitado: "#8b94a1"
  barra-solicitado: "#aeb6c7"
typography:
  headline:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
  note:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.5
  table-head:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.06em"
  stamp:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "0.7rem"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.05em"
  figure:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "0.82rem"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  bar: "2px"
  stamp: "3px"
  control: "4px"
  card: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  card-x: "24px"
  page-x: "32px"
components:
  button-default:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.texto}"
    rounded: "{rounded.control}"
    padding: "6px 14px"
    height: "36px"
  button-primary:
    backgroundColor: "{colors.riel-azul-noche}"
    textColor: "{colors.papel}"
    rounded: "{rounded.control}"
    padding: "6px 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.riel-azul-noche-hover}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.rojo-revision}"
    rounded: "{rounded.control}"
    padding: "6px 14px"
    height: "36px"
  button-danger-hover:
    backgroundColor: "{colors.rojo-revision-fondo}"
  stamp-neutral:
    backgroundColor: "transparent"
    textColor: "{colors.tinta-de-timbre}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "2px 8px"
  stamp-success:
    textColor: "{colors.verde-procesado}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "2px 8px"
  stamp-pending:
    textColor: "{colors.ambar-pendiente-texto}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "2px 8px"
  stamp-error:
    textColor: "{colors.rojo-revision}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "2px 8px"
  card:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.texto}"
    rounded: "{rounded.card}"
    padding: "20px 24px"
  field:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.texto}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
    height: "36px"
  table-header:
    backgroundColor: "{colors.papel-cabecera}"
    textColor: "{colors.texto-suave}"
    typography: "{typography.table-head}"
    padding: "9px 14px"
  nav-rail:
    backgroundColor: "{colors.riel-azul-noche}"
    textColor: "{colors.riel-texto}"
    width: "248px"
---

# Design System: TTDH Automation

## Overview

**Creative North Star: "La Oficina de Partes"**

El sistema es una oficina de partes digital: un riel azul noche a la izquierda, el trabajo sobre un gris frío, y cada estado de un documento estampado como el timbre fechador de recepción. Es una herramienta para un analista de operaciones que recorre tablas de volumen todo el día y no puede equivocarse en un RUT ni en un monto; la calma y la consistencia pesan más que el efecto.

La superficie es plana y de borde fino. La identidad vive en tres cosas: el riel, el sello de estado (borde de 2px, mayúsculas, monoespaciada) y las cifras en monoespaciada. El color acompaña, no informa solo: cada estado lleva su palabra escrita y su borde.

**Key Characteristics:**
- Riel lateral azul noche fijo de 248px; el trabajo ocurre sobre gris frío con tarjetas blancas de borde fino.
- Sellos de estado como único vocabulario de estado: texto, borde y color juntos.
- Fechas, RUT, ids y montos en monoespaciada con cifras tabulares.
- Superficie plana: sin sombras salvo en el diálogo modal.
- Movimiento sobrio, de 100 a 280 ms, solo para acompañar un cambio de estado.

## Colors

Paleta contenida: un azul noche que sirve de riel, de acción primaria y de texto; una tinta violeta de timbre para lo neutro o pendiente; verde, ámbar y rojo para el resultado, siempre con palabra.

### Primary
- **Azul Noche de Riel** (#16233f): riel lateral, botón primario y texto principal. Su variante de hover es #0f1a31 (`riel-azul-noche-hover`).
- **Tinta de Timbre** (#3d3a9e): sello neutro o informativo (Recibido), anillo de foco y selección de texto. Es el único acento.

### Secondary
- **Verde Procesado** (#1f7a46): procesado, normalizado, descontado; con fondo #edf6f0 en avisos de éxito.
- **Rojo de Revisión** (#b3261e): error, en revisión, y la acción irreversible con contorno.
- **Ámbar Pendiente** (#a35f00): pendiente de extracción y no descontado. Como texto se usa su variante oscura #7a4800 por contraste; fondo #fdf5e7.

### Neutral
- **Gris Frío de Trabajo** (#f5f6f8): fondo de página.
- **Papel** (#ffffff): tarjetas, campos, celdas. Variantes #f8f9fb (hover de fila, zona de carga) y #eef0f5 (cabecera de tabla).
- **Regla Fina** (#dde1ea): bordes de tarjetas y divisores. **Regla de Control** (#bfc6d4) para botones y zona de carga; **Regla de Campo** (#7c8798) para campos de formulario (3:1 sobre blanco).
- **Texto Suave** (#55617a) para secundario (6:1); **Texto de Ejemplo** (#667189) para placeholders (4,9:1).
- **Texto de Riel** (#c9d1e4) y **Texto Tenue de Riel** (#93a0be, 6:1 sobre el riel).

### Named Rules
**The Una Tinta Rule.** La tinta de timbre es el único acento; no se introduce un segundo color de marca. Su rareza es lo que hace que el sello se lea como sello.

**The Palabra Primero Rule.** El color nunca lleva un estado solo: siempre va con la palabra escrita y el borde. Verde procesado o descontado, ámbar pendiente o no descontado, rojo error o revisión, violeta neutro o recibido.

## Typography

**Display Font:** no hay display; el título de pantalla usa Public Sans.
**Body Font:** Public Sans 400/500/600/700 (con Segoe UI, system-ui, sans-serif), servida localmente.
**Label/Mono Font:** JetBrains Mono 500/700 (con ui-monospace, Cascadia Mono, Consolas), servida localmente.

**Character:** una sans de oficina, clara y sin gesto, contra una monoespaciada que pone el dato exacto (fecha, RUT, monto, sello) a la vista como tinta de máquina.

### Hierarchy
- **Headline** (700, 1.375rem, 1.5, -0.01em): título de pantalla; 1.2rem bajo 760px.
- **Title** (600, 1rem, 1.5): título de tarjeta; 1.05rem en diálogos.
- **Body** (400, 0.9rem, 1.5): texto de tarjetas, filas, campos. Los botones usan 0.875rem/500.
- **Note** (400, 0.8rem): ayudas, fechas de actualización y pies, en texto suave.
- **Table head** (700, 0.72rem, 0.06em, mayúsculas): cabeceras de tabla sobre fondo #eef0f5.
- **Stamp** (700, 0.7rem, 0.05em, mayúsculas, JetBrains Mono): sellos de estado.
- **Figure** (500 a 700, 0.82rem en tablas, 1.1rem en totales, JetBrains Mono, cifras tabulares): montos, deudores, ids, totales.

### Named Rules
**The Tinta de Máquina Rule.** Todo dato que el analista compara o copia (monto, id, fecha, total) va en monoespaciada con cifras tabulares y alineado a la derecha en tablas.

## Layout

Rejilla de dos columnas: riel de 248px fijo (sticky, alto completo) y área de trabajo con contenido de hasta 1440px, relleno 24px 32px y separación de 20px entre bloques. Las tarjetas se apilan; las filas de dos columnas usan 1.7fr y 1fr (mínimo 320px) y se pliegan a una columna bajo 1100px. El panel usa una rejilla auto-fit de mínimo 300px.

Ritmo de espaciado observado: 4, 8, 12, 16, 20, 24, 32px. Las tarjetas llevan 20px 24px de relleno y 16px entre sus partes; las tablas sangran a ras del borde de la tarjeta (margen -24px) y se desplazan dentro de su contenedor. Una tabla en tarjeta angosta (menos de 700px de contenedor) se convierte en lista apilada. Bajo 760px el riel pasa arriba, el menú se vuelve horizontal sin los módulos "Próximamente" y el estado de API y base de datos se conserva. Los totales se leen como una franja de planilla: celdas separadas por reglas finas.

## Elevation & Depth

Sistema plano y tonal: la profundidad la dan el gris frío de fondo, las tarjetas blancas con borde de 1px y el riel oscuro. No hay sombras en reposo ni en hover. La única sombra es la del diálogo modal.

### Shadow Vocabulary
- **Diálogo** (`box-shadow: 0 24px 48px rgb(16 27 44 / 0.16)`): solo el diálogo modal, con telón de rgb(16 27 44 / 0.4).

### Named Rules
**The Plano Salvo Diálogo Rule.** Las superficies son planas; solo lo que flota sobre la pantalla (el diálogo) lleva sombra.

## Shapes

Esquinas casi rectas, de papel y de sello: 3px en sellos, 4px en botones, campos y avisos, 6px en tarjetas, diálogos y zona de carga, 2px en barras de datos. Bordes de 1px en estructura; 2px solo en el sello y en la celda dudosa. Solo la zona de carga usa borde punteado. Círculos solo en puntos de estado (7px) y el icono de la zona de carga.

## Components

### Buttons
- **Shape:** esquina de 4px, alto mínimo 36px (30px compacto), relleno 6px 14px.
- **Primary:** azul noche con texto blanco; una acción principal por pantalla.
- **Default:** blanco con borde #bfc6d4. **Fantasma:** sin borde, texto azul noche en 600.
- **Hover / Focus:** hover solo con puntero fino (`hover: hover` y `pointer: fine`); el primario oscurece a #0f1a31, el secundario toma fondo #f8f9fb. Al pulsar escala 0.97 en 100 ms. Foco: contorno de 2px en tinta de timbre con 2px de separación (#c9c8f7 sobre el riel). El estado ocupado usa `aria-disabled`: se ve apagado pero sigue enfocable.
- **Peligro (irreversible):** contorno rojo (#b3261e), fondo transparente, aislado a la derecha de la fila de acciones con margen izquierdo automático.

### Sellos de estado
Etiqueta de borde de 2px, mayúsculas, JetBrains Mono 700 de 0.7rem, esquina de 3px. Texto y borde llevan el significado: violeta (neutro, Recibido), verde (procesado), ámbar (pendiente, texto oscuro), rojo (error). Sin rotación ni textura: se leen como etiqueta. El sello del último informe puede llevar la fecha de recepción en dd-mm-aa y se estampa al aparecer (180 ms, de escala 1.08 a 1).

### Cards / Containers
- **Corner Style:** 6px. **Background:** blanco. **Border:** 1px #dde1ea. **Shadow:** ninguna.
- **Internal Padding:** 20px 24px (16px bajo 760px). Título en Title; grupos internos se separan con una regla fina.

### Inputs / Fields
- **Style:** borde 1px #7c8798, esquina 4px, alto mínimo 36px, relleno 6px 10px, etiqueta encima en 600 de 0.85rem.
- **Focus:** contorno de tinta de timbre. **Error:** borde rojo con mensaje en rojo 0.8rem. **Celda dudosa de grilla:** borde de 2px ámbar con fondo ámbar claro.

### Tables
Cabecera en mayúsculas sobre #eef0f5, filas separadas por reglas finas, hover de fila #f8f9fb solo con puntero fino, columnas de cifras a la derecha en monoespaciada. Cada tabla llega con un fundido de fila de 140 ms.

### Navigation
Riel azul noche de 248px: marca (monograma "TT" en monoespaciada con borde de 2px), grupos en mayúsculas de 0.7rem, ítems de 0.9rem con relleno 8px 10px. Una sola pastilla (rgb(255 255 255 / 0.1)) se desliza hasta el módulo activo en 220 ms con `cubic-bezier(0.23, 1, 0.32, 1)`; el activo va en blanco y 600. Los módulos "Próximamente" van en texto tenue y sin enlace. Al pie, el estado del entorno con punto de 7px (verde #4cc38a conectado, rojo #f06a5f caído, latido mientras verifica).

### Barras de monto
Barras de 8px (2px de esquina) sobre #dde1ea cuyo largo es exacto: solicitado en #aeb6c7 y descontado en verde procesado dentro de él; la barra apilada de resultado del cruce mide 12px. Siempre con el porcentaje o la cifra escrita al lado.

### Totales (franja de planilla)
Celdas con reglas finas, etiqueta en 0.75rem 600 de texto suave y cifra en JetBrains Mono 700 de 1.1rem.

## Do's and Don'ts

### Do:
- **Do** dar a cada estado su sello: borde de 2px, mayúsculas, JetBrains Mono, con la palabra completa del estado.
- **Do** poner montos, ids, fechas y totales en JetBrains Mono con `tabular-nums`, alineados a la derecha en tablas.
- **Do** aislar la acción irreversible a la derecha de la fila, con contorno rojo y sin relleno, lejos de la acción principal.
- **Do** limitar el hover a `(hover: hover) and (pointer: fine)`.
- **Do** mantener el movimiento entre 100 y 280 ms con `cubic-bezier(0.23, 1, 0.32, 1)`, y con `prefers-reduced-motion` reducirlo a fundidos.
- **Do** usar la tinta de timbre (#3d3a9e) como único acento, y las variables de color en lugar de valores sueltos.

### Don't:
- **Don't** comunicar un estado solo con color: va con la palabra y el borde.
- **Don't** añadir sombras a tarjetas, botones o sellos; solo el diálogo flota.
- **Don't** rotar ni texturizar los sellos: se leen como etiqueta.
- **Don't** usar la tinta de timbre para decorar; no es color de marca de relleno.
- **Don't** poner animaciones largas o de entrada llamativa sobre filas de tabla: se miran decenas de veces al día.

## Notas de la ronda de revisión

- **Cuarta tinta, ámbar (`ambar-pendiente`, `#a35f00`; texto `#7a4800`):** se usa de forma deliberada solo para "advertencia": **No descontado**, **Pendiente** y el tramo "No descontados" de la barra del cruce. El contrato original nombraba tres tintas (violeta, rojo, verde); el ámbar se conserva porque PRODUCT.md exige distinguir "no descontado/pendiente" de "error/revisión", y el significado nunca depende solo del color (cada sello lleva su texto).
- **Una línea por sello:** en pantallas de 1400 px o más los sellos de las tablas no se parten; por debajo de ese ancho, y en celular, pueden ocupar dos líneas para que la tabla pierda ancho.
- **Acción principal del Cruce:** "Descargar informe a la TGR" es la acción primaria una vez cruzado el informe; "Volver a cruzar" es secundaria.
