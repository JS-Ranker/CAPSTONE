# Plan de presentación en vivo – TTDH Automation (12-nov-2026)

PPT: 20 láminas. Sugerido: ~20 min de exposición + demo de 6 min dentro de la lámina 19 + 5 min de preguntas.
Los tiempos son referenciales; ajustar al tiempo que dé la asignatura.

## 1. Reparto y guion por bloque

| Min | Láminas | Quién | Mensaje clave |
|---|---|---|---|
| 0:00–1:00 | 1–2 Portada y equipo | María | Presentar al equipo y el nombre del proyecto. |
| 1:00–3:00 | 3–5 Problema, flujo, objetivo | María | Hoy cada informe se escribe a mano; propusimos automatizar de punta a punta con trazabilidad. |
| 3:00–6:00 | 6–9 Lectura, pantalla, decisiones, revisión humana | David | Entra un documento (PDF, foto…), salen 9 datos; cada decisión tiene sello y motivo; lo dudoso lo revisa una persona. |
| 6:00–8:00 | 10 IA | Héctor | La IA avisa de lo raro (explicable + IsolationForest). |
| 8:00–9:30 | 11–12 Informe a la TGR y alcance | David | Un clic: Excel de respuesta + avisos. Hoy / lo que viene. |
| 9:30–12:00 | 15–16 Arquitectura y datos | Tomás | Tres capas, OCR local; esquemas dbo, stg→core, etl, banco, cruce, ia. |
| 12:00–15:00 | 13–14 Metodología y cronograma | María | Cascada con ajustes, 78 % real vs 85 % exigido: decirlo con honestidad. |
| 15:00–17:00 | 17–18 Resultados y obstáculos | Héctor | 302 pruebas, 7 formatos, 9 de 12 requisitos; qué nos enseñó cada obstáculo. |
| 17:00–23:00 | 19 **Demo en vivo** | Héctor maneja, David narra | Ver guion de la sección 2. |
| 23:00–28:00 | 20 Preguntas | Todos | Ver preguntas probables (sección 4). |

Nota: el PPT pone Arquitectura (15–16) antes de Metodología (13–14) solo en este reparto para que Tomás y María no se
intercalen; si prefieren el orden del PPT tal cual, el reparto de la tabla sigue funcionando con solo cambiar las filas.

## 2. Guion de la demo (lámina 19, ~6 min)

Documentos en `Fase 2\Evidencias Proyecto\Evidencias de sistema\Aplicación\data\simulados\`.

1. **Cargar un documento** (Ingesta): subir `no_estructurados\08_resolucion_foto.jpg` (la foto de celular; es el más vistoso).
   Decir: «es una foto con perspectiva, no un PDF limpio».
2. **Ver cómo se lee**: abrir el resultado: RUT, cliente, monto, expediente, tesorería, fecha. Comparar con la foto.
3. **Lo dudoso**: mostrar `11_resolucion_captura_baja_resolucion.png` → cae en Excepciones por confianza baja
   (alternativa: `05_resolucion_pdf_corrupto.pdf`). Corregir en la Bandeja y mostrar el historial.
4. **IA**: pantalla Análisis IA, mostrar el monto de 480 millones (`04_resolucion_pdf_texto_monto_anomalo.pdf`).
5. **Cruzar con el banco**: pantalla Cruce Banco, con la UTM del mes cargada; mostrar los sellos
   DESCONTADO / PARCIAL / NO DESCONTADO y el motivo.
6. **Descargar la respuesta**: Excel para la TGR (Resumen, Detalle) y lista de avisos.
7. **Dashboard**: cerrar con las cifras y decir «cada paso deja su fecha y su motivo».

## 3. Preparación y plan B

Antes (idealmente la noche anterior y 30 min antes de exponer):
- SQL Server `MSSQLSERVER` corriendo; API en <http://localhost:8000/docs>; web en <http://localhost:5173>.
  (Hoy quedaron levantadas; se detienen con Ctrl+C en sus ventanas.)
- **La BD ya tiene datos de pruebas previas** (5 archivos, 244 casos, 936 cuentas, 2 UTM). Dos riesgos: el sistema rechaza
  duplicados, así que un documento ya cargado saldrá como «duplicado»; y el dashboard mostrará cifras viejas.
  Decidan antes: o usan documentos que no hayan subido, o reinician la BD con los scripts de `Base de datos\`
  (ojo: `02_tablas.sql` borra todo; ver INSTALACION.md §4). Lo recomendable: ensayar completo con la BD limpia.
- Verificar UTM del mes cargada, o el cruce no correrá.
- Verificar Tesseract instalado (idioma `spa`), o las fotos fallan.
- Ventana de navegador en pantalla completa, zoom 110–125 %, notificaciones apagadas, carpeta `simulados` abierta.
- Wi-Fi: la demo funciona 100 % local, no depende de internet.

Plan B si algo falla en vivo:
- Tener capturas o un video corto (2 min) de la demo completa en el PPT/escritorio.
- Tener generado de antemano `respuesta_tgr.xlsx` para mostrarlo aunque el cruce falle.
- Si el OCR demora, avisar «esto corre en local, sin servicios externos» y seguir hablando de la lámina 15.

## 4. Preguntas probables y respuesta corta

- **¿Con datos reales?** No: aún no hay documentos ni clientes reales; 22 simulados con el formato de las resoluciones.
- **¿Por qué no hay oficios/cargo real?** El sistema calcula e informa; el cargo real lo hace el core del banco.
- **¿Y si el OCR se equivoca?** Lo dudoso pasa a la Bandeja de Excepciones; nunca se adivina un dato.
- **¿Qué regla aplica el descuento?** Saldo total del cliente < 0,5 UTM → no se descuenta; si no, min(saldo, deuda),
  desde la cuenta de mayor saldo; varias deudas del mismo RUT, de la más antigua a la más nueva.
- **¿Cómo participa la IA?** Reglas explicables + IsolationForest que alerta solo lo más raro del historial; falta la consulta en lenguaje natural.
- **¿Por qué 78 % y no 85 %?** El alcance creció y se rehízo el modelo con el formato real; priorizamos lo crítico y cerramos con pruebas.
- **¿Seguridad / datos sensibles?** OCR local, sin enviar documentos a terceros; falta roles y permisos (lo que viene).
- **¿Por qué 9 de 12 requisitos?** Los 3 faltantes están en «lo que viene»: roles, lenguaje natural, comparación entre ejecuciones y exportar PDF/CSV.

## 5. Ensayo

1. Ensayo completo con cronómetro (28 min), con la BD limpia.
2. Segundo ensayo solo de la demo, 2 veces seguidas.
3. Cada integrante conoce la lámina del compañero anterior para hacer el empalme.
