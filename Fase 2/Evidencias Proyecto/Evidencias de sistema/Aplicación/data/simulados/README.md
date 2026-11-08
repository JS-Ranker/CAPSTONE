# Documentos simulados de la TGR

Resoluciones de retención **ficticias**, con el diseño de los documentos del banco: un deudor por documento, en dos
páginas (expediente y RUT en los "vistos", monto en el "resuelvo", ID de demanda, N° de resolución, firma y fecha en la
segunda página). El diseño lo da `backend/scripts/1. creacion documentos extendido.py` (de David); `backend/scripts/generar_datos_simulados.py`
parte de ese PDF y arma las variantes por formato y por escenario.

```
cd backend
python scripts/generar_datos_simulados.py            # vuelve a escribir esta carpeta (misma semilla, mismo resultado)
```

`manifiesto.json` dice, para cada archivo, qué debe pasar: estado de la extracción, si queda para revisión manual, de
qué archivo es reenvío y los datos esperados del deudor. Las pruebas (`backend/tests/test_resoluciones.py`) comparan la
extracción con ese manifiesto y comprueban que esta carpeta sea la que produce el script.

Todo es ficticio: los RUT van de 40.000.000 a 49.999.999 (fuera de los rangos de personas y empresas) y el banco se llama
"Banco Genérico". **Nunca** agregar documentos reales.

## `no_estructurados/`

| Archivo | Qué es | Resultado esperado |
|---|---|---|
| `01_resolucion_pdf_texto.pdf` | PDF con texto, el documento base | Normalizado, los 9 datos leídos sin OCR |
| `02_resolucion_pdf_texto_otra_tesoreria.pdf` | Otro deudor, otra tesorería y otro monto | Normalizado |
| `03_resolucion_pdf_texto_reenvio.pdf` | Copia idéntica del 01 | La recepción lo rechaza como duplicado |
| `04_resolucion_pdf_texto_monto_anomalo.pdf` | Monto de 480 millones | Normalizado; la IA lo marca como anomalía |
| `05_resolucion_pdf_corrupto.pdf` | PDF dañado | Error de Extracción: revisión manual del documento |
| `06_resolucion_escaneada.pdf` | Escaneo limpio, apenas girado | Normalizado (OCR) |
| `07_resolucion_escaneada_con_ruido.pdf` | Escaneo con ruido y giro mayor | Normalizado (OCR) |
| `08_resolucion_foto.jpg` | Foto de celular de las dos hojas, con perspectiva | Normalizado (OCR) |
| `09_resolucion_foto_con_sombra.jpg` | Foto con más inclinación y sombra | Normalizado (OCR) |
| `10_resolucion_captura.png` | Captura de pantalla nítida de las dos hojas | Normalizado (OCR) |
| `11_resolucion_captura_baja_resolucion.png` | Captura reducida a poco más de 80 dpi | Normalizado, con confianza baja: queda para revisión |

## `estructurados/`

En Word y TXT va el mismo texto de la resolución; en Excel y CSV, filas `campo; valor`.

| Archivo | Qué es | Resultado esperado |
|---|---|---|
| `12_resolucion_valida.xlsx` | Excel válido | Normalizado |
| `13_resolucion_valida_reenvio.xlsx` | Copia idéntica del 12 | Rechazado como duplicado |
| `14_resolucion_valida.csv` | CSV válido (UTF-8, `;`) | Normalizado |
| `15_resolucion_valida.docx` | Word válido | Normalizado |
| `16_resolucion_latin1.txt` | Texto plano ISO-8859-1 | Normalizado |
| `17_resolucion_sin_monto.xlsx` | Falta el monto solicitado | El ETL lo rechaza (RN05) y queda en la Bandeja de Excepciones |
| `18_resolucion_sin_monto.docx` | El texto no trae el monto | Igual que el 17 |
| `19_resolucion_rut_invalido.csv` | El dígito verificador no corresponde | El ETL lo rechaza (RN01) |
| `20_resolucion_corrupta.xlsx` | Excel dañado | Error de Extracción: revisión manual del documento (RN04) |
| `21_resolucion_vacia.csv` | Archivo vacío | Error de Extracción |
| `22_informe_otro_formato.csv` | No es una resolución de la TGR | Error de Extracción |

## `banco_generico/`

`cuentas_core_bancario.csv` es el core bancario simulado (se carga con `backend/scripts/cargar_core_bancario.py`). Trae
las cuentas de los deudores de los documentos válidos, con saldos que recorren la regla del cruce:

- clientes con saldo suficiente para cubrir la deuda (se descuenta todo);
- clientes con saldo que cubre solo una parte (se descuenta el saldo);
- clientes con saldo total bajo 0,5 UTM (no se descuenta nada);
- deudores que no son clientes del banco (sin cuentas), y algunas cuentas bloqueadas o cerradas que el cruce ignora;
- además, clientes del banco que no tienen deuda.

## Para las pruebas con varios deudores por archivo

Las pruebas de la lectura de tablas, de las sumatorias de control, del ETL por lotes y de la IA usan informes con tabla
(varios deudores por archivo) que arma `backend/tests/fabrica_informes.py` en la caché de pytest. No son documentos del
banco y no se guardan aquí.
