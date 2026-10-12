"""Proceso ETL de casos TGR: CSV -> stg.casos_tgr -> core.casos_tgr, con las reglas de Normalizar_TGR.ktr.

reglas.py: normalización y validación de una fila (sin base de datos).
carga.py: ejecución completa, con duplicados, resultados por fila (etl.resultados) y bitácora.

Requerimientos: RF02, RF03, RN04
Responsable: Tomás Catalán (modelo y reglas, en los .ktr de "Base de datos"); versión Python: Héctor Sanhueza
"""
