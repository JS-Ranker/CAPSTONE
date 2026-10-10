# Datos simulados

Nóminas TGR **ficticias** para desarrollar y probar los módulos de TTDH Automation. No contienen datos reales: los RUT están entre 40.000.000 y 49.999.999, un rango que hoy no se asigna a personas ni a empresas, y todos los documentos dicen "DOCUMENTO SIMULADO".

Se generan con un script, así que **no se editan a mano**:

```bash
cd backend
python scripts/generar_datos_simulados.py                  # regenera esta carpeta (mismo resultado siempre)
python scripts/generar_datos_simulados.py --grande 12000   # agrega 90_nomina_volumen.csv para pruebas de rendimiento
```

## Plantilla estándar de carga (propuesta v1)

Todos los formatos tienen la misma estructura (RF02, RN04):

| Línea | Contenido |
|---|---|
| 1. Encabezado | `ENCABEZADO; TGR; <lote>; <fecha AAAA-MM-DD>; <cantidad de registros>` |
| 2. Columnas | `id_transaccion; rut_deudor; nombre_deudor; folio_deuda; monto; fecha_origen; cuenta_destino; codigo_banco; tipo_movimiento` |
| 3…n. Detalle | Una transacción por línea |
| Última. Pie | `TOTALES; <cantidad de registros>; <suma de montos>` |

- `rut_deudor` normalizado: `12345678-9`. `monto` en pesos, entero. `tipo_movimiento`: `Depósito`, `Devolución` o `Traspaso`. `codigo_banco` de Banco Genérico: `099`.
- Obligatorios según RN03: monto, cuenta_destino, codigo_banco y tipo_movimiento.
- Clave de duplicado según RN02: id_transaccion + rut_deudor + monto + fecha_origen.

## Archivos

| Archivo | Qué prueba | Resultado esperado |
|---|---|---|
| `estructurados/01_nomina_valida.xlsx` | Excel con celdas de número y fecha | Procesado, 150 válidos |
| `estructurados/02_nomina_valida.csv` | CSV UTF-8 con `;` | Procesado, 120 válidos |
| `estructurados/03_nomina_latin1.txt` | TXT ISO-8859-1 con `\|` | Procesado, 80 válidos |
| `estructurados/04_nomina_casos_borde.xlsx` | Un caso por regla: RUT inválidos, campos faltantes, formatos de monto y fecha, duplicado | 20 válidos, 10 inválidos, 1 duplicado |
| `estructurados/05_nomina_lote2_con_duplicados.csv` | Repite 5 transacciones de 02 | 5 duplicados (si 02 se procesó antes) |
| `estructurados/06` a `10` | Totales o cantidad que no cuadran, sin pie, columnas incorrectas, archivo corrupto | Error |
| `estructurados/11_nomina_vacia.csv` | Nómina sin registros | **Por definir** (el ERS no lo dice) |
| `estructurados/12_nomina_valida_reenvio.xlsx` | Copia exacta de 01 | Rechazado: archivo ya procesado |
| `no_estructurados/21_nomina_pdf_texto.pdf` | PDF con tabla seleccionable | Procesado, 25 válidos |
| `no_estructurados/22_…_totales_no_cuadran.pdf` | Total impreso incorrecto | Revisión manual (CU12 5b) |
| `no_estructurados/23_nomina_escaneada.pdf` | Escaneo de buena calidad (solo imagen) | Procesado, 25 válidos |
| `no_estructurados/24_foto_nomina.jpg` | Foto con perspectiva, sombra y 3 montos manchados | 3 a "Revisión de Extracción" |
| `banco_generico/cuentas_core_bancario.csv` | Cuentas de Banco Genérico para el cruce (RF04) | 13 casos que no calzan: cuenta cerrada, inexistente o de otro RUT |

**`manifiesto.json`** tiene, para cada archivo y cada registro, los valores normalizados y el resultado esperado. Las pruebas de cada módulo deberían compararse contra él en lugar de repetir los valores a mano.

## Nota para la extracción (OCR)

Con Tesseract sobre la **página completa**, las líneas de la tabla hacen que se salte filas enteras, incluso en una imagen limpia. Leyendo **celda por celda** (detectar la grilla y recortar cada celda), el PDF escaneado da los 25 montos con confianza de 90% o más, y los montos manchados de la foto no se leen con confianza, por lo que van a revisión, como exige RN05.

## Pendientes para el equipo

- Confirmar la plantilla (columnas, encabezado y pie) con Tomás (ETL) y David (validaciones).
- La tabla `Registros_TGR` no tiene `cuenta_destino`, `codigo_banco`, `tipo_movimiento`, `nombre_deudor` ni `id_transaccion`, aunque el ERS los usa en RN02, RN03 y CU12. Tampoco tiene un estado para "Excepciones por Datos Faltantes" (RN03); por ahora el manifiesto los marca como `Inválido` con motivo RN03.
- Definir qué hacer con una nómina sin registros (archivo 11).
- La regla de cruce es una sugerencia: todo lo que no calza aparece como "Rechazado Banco".
