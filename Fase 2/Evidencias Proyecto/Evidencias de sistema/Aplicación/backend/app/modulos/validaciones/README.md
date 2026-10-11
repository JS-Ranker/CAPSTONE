# Módulo de validaciones: qué hay que construir

**Responsable:** David Muñoz · **Requerimientos:** RF03, RN01, RN02, RN03 (y RN05 para OCR) · **Caso de uso:** CU03, paso 5

## En una frase

Recibir los registros de una nómina (cada fila es un deudor) y decidir para cada uno si está **Válido**, **Inválido**, **Duplicado** o en **Revisión de Extracción**, con el motivo. Solo los válidos pasan al cruce con el banco.

## Dónde encaja

```
Recepción (Héctor) ✅ → ETL (Tomás) → VALIDACIONES (David) → Cruce con el banco
                         lee el archivo     revisa cada registro
```

Antes de este módulo, el **ETL (Tomás)** se encarga de:
- revisar el **archivo completo** (RN04): estructura, encabezado, pie, columnas y codificación;
- verificar que los totales cuadren (CU03 pasos 1 a 3).

Si el archivo falla, se marca "Error" completo y **no llega a validaciones**. Son los casos 06, 07, 08, 09 y 10 de los datos simulados.

**A este módulo le llegan solo los registros de archivos sanos.** La división entre ETL y validaciones es una propuesta basada en los encabezados de cada módulo: confírmenla entre ustedes.

### Qué recibe

Una lista de registros con las 9 columnas de la plantilla estándar. Son las mismas que usa la extracción (`extraccion/plantilla.py`):

`id_transaccion`, `rut_deudor`, `nombre_deudor`, `folio_deuda`, `monto`, `fecha_origen`, `cuenta_destino`, `codigo_banco`, `tipo_movimiento`

Si el registro viene de un PDF escaneado o una foto, trae además la **confianza del OCR** (0 a 100).

**Por definir con Tomás:** el formato exacto en que el ETL entrega los registros (lista de diccionarios, DataFrame de pandas, etc.).

## Las reglas, una por una

### 1. Campos obligatorios (RN03)
| Obligatorios | No obligatorios |
|---|---|
| `monto`, `cuenta_destino`, `codigo_banco`, `tipo_movimiento` | `nombre_deudor`, `folio_deuda` |

Si falta uno → el ERS dice "Excepciones por Datos Faltantes". La tabla no tiene ese estado (ver "Problemas de la base de datos"), así que por ahora va como **Inválido** con motivo `RN03 - Falta <campo>`.

### 2. RUT con Módulo 11 (RN01)
- **Primero normalizar y después validar.** Estos casos son válidos:
  - `12.345.678-5` (con puntos);
  - ` 12345678-5 ` (con espacios);
  - `10000013-k` (con k minúscula).
- Si el formato es imposible (letras en el número, etc.) o el dígito verificador no calza → **Inválido** (Error de Formato).
- **Ya está hecho, solo reutilízalo:** `normalizar_rut()` y `rut_valido()` en `app/modulos/extraccion/normalizacion.py`.

### 3. Formatos (RF03)
| Campo | Válido | Inválido |
|---|---|---|
| `monto` | `1500000`, `$ 1.500.000` | texto que no es número |
| `fecha_origen` | `2026-09-15`, `15-09-2026`, `15/09/2026` | `31-02-2026`, `ayer` |
| `tipo_movimiento` | `Depósito`, `Devolución`, `Traspaso` | cualquier otro valor |

`normalizar_monto()` y `normalizar_fecha()` también existen en `normalizacion.py`. **Ojo:** si no pueden convertir, devuelven el texto sin cambios; tu módulo debe detectarlo y marcar el registro como Inválido.

**Montos:** usar enteros o `Decimal`, **nunca `float`**, porque es dinero.

### 4. Duplicados (RN02)
- **Clave:** `id_transaccion` + `rut_deudor` + `monto` + `fecha_origen`. Si coinciden las 4 → duplicado.
- **Mismo ID pero otro monto → NO es duplicado.** El archivo 04 tiene ese caso a propósito.
- **Hay que comparar en dos niveles:**
  - **dentro del mismo archivo:** el primero queda Válido y los siguientes Duplicado;
  - **contra archivos procesados antes**, que están en la base. Por eso el archivo 05 tiene 5 duplicados **solo si el 02 se procesó primero**.
- **Comparar después de normalizar**, para que `12.345.678-5` y `12345678-5` cuenten como el mismo RUT.

### 5. Confianza del OCR (RN05), solo para PDF escaneados y fotos
- Si la confianza de los campos críticos (RUT, monto y cuenta) es **menor a 90%** → **Revisión de Extracción**.
- El cálculo ya existe: `RegistroExtraido.requiere_revision` en `extraccion/plantilla.py`.
- **Pendiente de Héctor:** hoy la planilla CSV que genera la extracción no incluye la confianza de cada registro. Hay que agregarla para que llegue hasta aquí.

### Si un registro falla varias reglas
**Propuesta (decidirla en equipo):** guardar **todos** los motivos, pero un solo estado, con esta prioridad:

1. Revisión de Extracción;
2. Inválido (obligatorios, formato, RUT);
3. Duplicado;
4. Válido.

Un registro inválido no se revisa como duplicado.

## Qué entrega

Para cada registro, su **estado** y sus **motivos**, guardados en `Registros_TGR` (CU03 paso 6). Una forma simple de construirlo, como sugerencia:

```python
@dataclass
class ResultadoValidacion:
    estado: str            # 'Válido', 'Inválido', 'Duplicado' o 'Revisión de Extracción'
    motivos: list[str]     # p. ej. ['RN01 - RUT no pasa Módulo 11']

def validar_registro(valores: dict[str, str], confianza: float | None = None) -> ResultadoValidacion: ...
def validar_lote(registros, claves_ya_procesadas: set) -> list[ResultadoValidacion]: ...
```

Si las reglas son **funciones puras** (sin base de datos), se prueban rápido y sin SQL Server. Solo la consulta de "claves ya procesadas" necesita la base.

## ⚠️ Problemas de la base de datos (hay que resolverlos con Tomás)

La tabla `Registros_TGR` (en `Base de datos/02_tablas.sql`) **no alcanza** para estas reglas:

| Falta | Por qué hace falta |
|---|---|
| `id_transaccion` | Es parte de la clave de duplicados (RN02) |
| `cuenta_destino`, `codigo_banco`, `tipo_movimiento` | Son obligatorios (RN03) y los necesita el cruce |
| `nombre_deudor` | Viene en la nómina |
| `motivo_validacion` | Para saber **por qué** un registro es inválido (la Bandeja de Excepciones, RF05, lo necesita) |
| Estado "Datos Faltantes" | RN03 y CU03 5c lo piden; hoy el CHECK solo permite Válido, Inválido, Duplicado y Revisión de Extracción |

**Sugerencia:** un script `06_validaciones.sql` que agregue estas columnas sin borrar datos, igual que `04_recepcion.sql`.

## Cómo probarlo: los resultados correctos ya existen

En `data/simulados/` hay nóminas de prueba, y `manifiesto.json` dice **qué estado debe quedar cada registro** (campo `estado_esperado`):

| Archivo | Resultado esperado |
|---|---|
| `04_nomina_casos_borde.xlsx` | **Un caso por regla:** 20 válidos, 10 inválidos y 1 duplicado, cada uno con su motivo |
| `05_nomina_lote2_con_duplicados.csv` | 55 válidos y 5 duplicados (si el 02 se procesó antes) |
| `01`, `02`, `03`, `21`, `23` | Todos válidos |
| `24_foto_nomina.jpg` | 3 registros en Revisión de Extracción |

Las pruebas van en `backend/tests/` con pytest. En `tests/conftest.py` está la fixture `conexion`: abre una transacción en SQL Server y la revierte al final, así las pruebas no dejan datos.

## Por definir en equipo
1. Qué pasa con una nómina sin registros (`11_nomina_vacia.csv`): el ERS no lo dice.
2. La prioridad entre estados cuando un registro falla varias reglas.
3. El formato de entrega entre el ETL y validaciones.
4. Los cambios en `Registros_TGR`.
