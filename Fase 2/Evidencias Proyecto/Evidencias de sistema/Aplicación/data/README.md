# Datos de prueba

Esta carpeta contiene **solo datos y documentos simulados** para desarrollar y probar los módulos de TTDH Automation.

- `simulados/`: resoluciones de retención ficticias de la TGR (un deudor por documento, con el diseño de los documentos del banco) en PDF con texto, PDF escaneado, JPG, PNG, Word, TXT, Excel y CSV, con casos válidos y con problemas (dato faltante, RUT inválido, reenvío repetido, monto anómalo, archivos dañados o vacíos), más una base simulada de cuentas de Banco Genérico. Se generan con `backend/scripts/generar_datos_simulados.py`; el detalle está en [simulados/README.md](simulados/README.md).
- `muestra_tgr/`: el CSV de ejemplo del modelo de Tomás para probar el ETL (ver su README).
- **Nunca** agregar datos reales de deudores de la TGR ni de Banco Genérico. Las carpetas `real/`, `entrada/` y `salida/` están excluidas del repositorio en el `.gitignore`.

Responsables de los datos simulados: María Trinidad Gaete y Héctor Sanhueza (Acta N° 6).
