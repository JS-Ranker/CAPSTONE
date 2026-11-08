# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Analista de operaciones de Banco Genérico (confirmado). Trabaja a diario en un computador de escritorio: recibe los informes de retención de la Tesorería General de la República (TGR), revisa lo que el sistema no pudo leer o validar, corrige datos dudosos, controla el cruce con las cuentas del banco y descarga lo que se devuelve a la TGR. Su trabajo es repetitivo y de volumen: necesita recorrer tablas rápido y no equivocarse en RUT ni montos.

Lectores secundarios (visto en el proyecto, no priorizados): jefatura y auditoría que miran el Dashboard y descargan informes. El rediseño sirve primero al analista.

## Product Purpose

TTDH Automation automatiza el procesamiento de los informes de deudores que la TGR envía al banco. Recibe el documento por correo, SFTP o carga web (PDF, escaneo, foto, Word, Excel, CSV, TXT); extrae al deudor (con OCR local); valida y carga cada caso (ETL); lo cruza con las cuentas del banco aplicando la regla de retención; deriva lo dudoso a revisión manual; analiza el conjunto con IA; y entrega el informe de respuesta a la TGR y la lista de avisos a clientes. El éxito es que el analista cierre un informe sin reescribir datos a mano y con cada paso trazable.

Es el proyecto Capstone (APT) de Duoc UC del equipo STARTAB, con datos simulados.

## Positioning

A diferencia de una planilla o un ETL genérico, une en una sola cadena trazable la lectura de documentos reales de la TGR (incluidas fotos y escaneos), la regla de retención del banco (0,5 UTM, cuenta de mayor saldo, deuda más antigua) y la revisión humana de lo dudoso, con el motivo de cada decisión a la vista.

## Operating Context

Flujo: Ingesta → Casos TGR → Excepciones → Cruce Banco → informes (Excel) → Dashboard. Cada documento tiene un estado (Pendiente de Extracción, Procesado, Error de Extracción). El cruce usa la UTM del mes, que ingresa el analista o se obtiene de la fuente oficial. El sistema solo calcula: el cargo real lo hace el core bancario. No envía correos: genera la lista de avisos.

Pantallas actuales: Ingesta, Dashboard, Casos TGR, Excepciones, Análisis IA, Cruce Banco; "Próximamente": Reportes, Auditoría, Usuarios y roles.

## Capabilities and Constraints

- Frontend React + Vite (JavaScript, sin TypeScript), CSS propio en `src/App.css`, ruteo por hash (`#/panel`, `#/cruce?informe=1527`), backend FastAPI en `/api`.
- Terminología fija (confirmado, no cambiar): TGR, Banco Genérico, RUT, resolución, expediente, UTM, Bandeja de Excepciones, Cruce, Descontado / Descontado parcial / No descontado / En revisión.
- Funciones y flujos actuales no cambian: el rediseño es de apariencia, jerarquía y orden visual.
- Los colores de estado hoy significan algo (verde procesado o descontado, ámbar pendiente o no descontado, rojo error o revisión); el rediseño puede cambiar su tono pero no pierde la distinción, y nunca depende solo del color.
- Sin inicio de sesión todavía (roles y permisos no construidos).

## Brand Commitments

Nombre del producto: TTDH Automation. Entidad: Banco Genérico (nombre que anonimiza al banco real). Equipo: STARTAB. No hay logo oficial: la marca actual es el monograma "TT" provisional.

## Evidence on Hand

Datos simulados completos: 22 documentos de la TGR en todos los formatos (`data/simulados`), base bancaria simulada, y una base de desarrollo con 244 casos reales de prueba. No existen documentos, clientes ni cifras reales; no se deben inventar.

## Product Principles

1. El dato dudoso nunca se oculta: lo que el sistema no pudo leer con confianza se ve y se puede corregir.
2. Cada decisión lleva su motivo: por qué se descontó, por qué no, por qué se rechazó.
3. La pantalla sirve al volumen: tablas escaneables y estables antes que decoración.
4. Una acción principal por pantalla, clara.
5. Es una herramienta de trabajo diaria; la calma y la consistencia valen más que el efecto.

## Accessibility & Inclusion

Hoy la app usa etiquetas ARIA, regiones `aria-live` y contraste cuidado (visto en el código). No hay una norma exigida por escrito: se mantiene el nivel actual como mínimo (contraste AA, uso con teclado, estado nunca solo por color).
