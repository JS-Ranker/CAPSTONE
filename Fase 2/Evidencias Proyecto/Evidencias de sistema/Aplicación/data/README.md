# Datos de prueba

Esta carpeta contiene **solo datos y documentos simulados** para desarrollar y probar los módulos de TTDH Automation.

- `simulados/`: nóminas ficticias en Excel, CSV, PDF con texto, PDF escaneados y fotografías, con casos válidos y casos de borde (RUT inválidos, duplicados, campos vacíos, montos que no cuadran con los totales de control). Se generan con `backend/scripts/generar_datos_simulados.py`; el detalle está en [simulados/README.md](simulados/README.md).
- **Nunca** agregar datos reales de deudores de la TGR ni de Banco Genérico. Las carpetas `real/`, `entrada/` y `salida/` están excluidas del repositorio en el `.gitignore`.

Responsables de los datos simulados: María Trinidad Gaete y Héctor Sanhueza (Acta N° 6).
