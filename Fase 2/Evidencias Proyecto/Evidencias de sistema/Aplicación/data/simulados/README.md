# Datos simulados

Informes de deudores de la TGR **ficticios** para desarrollar y probar TTDH Automation. No contienen datos reales: los RUT están entre 40.000.000 y 49.999.999, un rango que hoy no se asigna a personas ni a empresas, y todos los documentos dicen "DOCUMENTO SIMULADO".

Se generan con un script, así que **no se editan a mano**:

```bash
cd backend
python scripts/generar_datos_simulados.py                  # regenera esta carpeta (mismo resultado siempre)
python scripts/generar_datos_simulados.py --grande 12000   # agrega 90_informe_volumen.csv para pruebas de rendimiento
```

## El informe de deudores

La TGR envía por correo un informe con un deudor por fila, en cualquiera de estos formatos: Excel, CSV, TXT, Word, PDF con texto, PDF escaneado o foto. Todos tienen la misma estructura:

| Parte | Contenido |
|---|---|
| Encabezado | `Lote: <lote>   Fecha de generación: <dd-mm-aaaa>   Registros: <n>` |
| Títulos | `RUT · Nombre · ID Demanda · N° Resolución · Monto Solicitado · Tipo Embargo · Expediente · Tesorería · Fecha Oficio` |
| Detalle | Un deudor por fila |
| Totales | `TOTALES   Registros: <n>   Monto total: $ <suma>` (sumatorias de control, RN05) |

Las columnas son las que, según el equipo, vienen de la TGR en el CSV del ETL de Tomás. El resto de las columnas de ese CSV (fecha de ingreso, múltiples roles, revisión manual, campos faltantes, remitente…) las agrega el proceso al extraer el informe (`backend/app/modulos/etl/desde_informe.py`).

- RUT `12345678-9` (en PDF, imágenes y Word se imprime con puntos). Monto en pesos, entero. Expediente `número-año localidad`.
- Datos críticos (RN05): RUT, monto solicitado y expediente. Si se leen con confianza bajo 90 %, o si falta un dato, el deudor se carga marcado para **revisión manual** y queda en la Bandeja de Excepciones.
- Las reglas del ETL (RUT válido, expediente con formato, fechas, duplicados) son las de `Normalizar_TGR.ktr`.

## Archivos

| Archivo | Qué prueba | Resultado esperado del informe |
|---|---|---|
| `estructurados/01_informe_valido.xlsx` | 150 deudores, celdas numéricas y de fecha | Procesado |
| `estructurados/02_informe_valido.csv` | 120 deudores, UTF-8 separado por `;` | Procesado |
| `estructurados/03_informe_latin1.txt` | 80 deudores, ISO-8859-1 separado por `\|` | Procesado |
| `estructurados/04_informe_casos_borde.xlsx` | Un caso por regla: RUT con puntos, k minúscula, DV malo, sin monto, monto en palabras, fecha inexistente, sin fecha, expediente sin formato, sin nombre, mismo RUT con dos expedientes, duplicado… | Procesado (cada deudor con su resultado en el manifiesto) |
| `estructurados/05_informe_mes2_con_repetidos.csv` | Repite 5 deudores de 02 | Procesado |
| `estructurados/06_informe_totales_no_cuadran.csv` | La suma de los totales no cuadra | Error de Extracción |
| `estructurados/07_informe_cantidad_no_cuadra.xlsx` | Declara 43 deudores y trae 40 | Error de Extracción |
| `estructurados/08_informe_sin_totales.csv` | Sin la línea TOTALES | Procesado |
| `estructurados/09_informe_columnas_incorrectas.csv` | Falta Expediente y el monto se llama "Importe" | Error de Extracción |
| `estructurados/10_informe_corrupto.xlsx` | Bytes aleatorios | Error de Extracción |
| `estructurados/11_informe_vacio.csv` | Sin deudores | Error de Extracción |
| `estructurados/12_informe_valido_reenvio.xlsx` | Copia exacta de 01 | Rechazado en la recepción (ya recibido) |
| `estructurados/13_informe_valido.docx` | 40 deudores en una tabla de Word | Procesado |
| `no_estructurados/21_informe_pdf_texto.pdf` | Tabla con texto seleccionable | Procesado |
| `no_estructurados/22_informe_pdf_texto_totales_no_cuadran.pdf` | El total impreso no cuadra | Error de Extracción |
| `no_estructurados/23_informe_escaneado.pdf` | Solo imagen (OCR) | Procesado; los dudosos, a revisión |
| `no_estructurados/24_foto_informe.jpg` | Foto con perspectiva, sombra y 3 montos manchados | Error de Extracción |
| `banco_generico/cuentas_core_bancario.csv` | Cuentas de Banco Genérico | Base provisoria: el cruce con saldos y la regla de 0,5 UTM viene después |

`manifiesto.json` trae el resultado esperado de cada deudor (`Cargado`, `Revisión manual`, `Rechazado` o `Duplicado`) y lo usan las pruebas (`backend/tests/test_extraccion.py`, `test_datos_simulados.py` y `test_recepcion_canales.py`).
