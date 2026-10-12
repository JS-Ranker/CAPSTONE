# Muestra TGR para el ETL

CSV de muestra en el formato que carga el ETL de Pentaho (`Evidencias de sistema/Base de datos/`).
**Datos ficticios**: los RUT van entre 40.000.000 y 49.999.999, fuera de los rangos asignados hoy.

| Archivo | Contenido |
|---|---|
| `resultado_tgr_20261012.csv` | 35 oficios: 24 válidos y 11 casos de borde |
| `esperado.json` | Resultado que debería tener cada fila al pasar por `Normalizar_TGR.ktr` |

Formato: UTF-8 con BOM, separador `;`, encabezado en la primera fila y las 21 columnas de
`transformacion_carga.ktr` en el mismo orden. Fechas en `dd-MM-yyyy`.

## Resultado esperado

| Cantidad | Resultado |
|---:|---|
| 28 | Carga en `core.casos_tgr` |
| 2 | Rechazado en `Validar_Indicadores` (múltiples roles o revisión manual distinto de SI/NO) |
| 3 | Rechazado en `Validar_Llave_Caso` (DV incorrecto, expediente sin formato, sin fecha de ingreso) |
| 2 | Descartado en `Detectar_Duplicados` (mismo RUT, DV, rol y fecha de ingreso) |

Para probar el ETL: apuntar el `CSV file input` de `transformacion_carga.ktr` a este archivo, ejecutar
las dos transformaciones y comparar `SELECT COUNT(*) FROM core.casos_tgr` con el resumen de arriba.

## Regenerar

Desde `backend/`:

```
python scripts/generar_muestra_tgr.py
```

Con la misma semilla el archivo sale idéntico. `--validos N` cambia la cantidad de filas válidas.
