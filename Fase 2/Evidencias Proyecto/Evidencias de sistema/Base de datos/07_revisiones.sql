/* =============================================================
   TTDH Automation - 07. Revisión manual de excepciones (RF05, RN05, CU05, RF10)
   Historial de cada revisión hecha en la Bandeja de Excepciones. Hay dos tipos de excepción:
   - un caso de core.casos_tgr marcado para revisión manual (rev_manual_bit = 1), y
   - una fila que el ETL rechazó (etl.resultados con resultado = 'Rechazado').
   Cada acción agrega una fila (no se modifican ni borran): el estado actual es el de la última.
   No modifica stg.casos_tgr ni core.casos_tgr. Se puede ejecutar más de una vez y no borra datos.
   Ejecutar después de 06_etl.sql: sqlcmd -S localhost -E -C -f 65001 -i 07_revisiones.sql
   ============================================================= */

USE TTDH_Automation;
GO

IF OBJECT_ID(N'etl.revisiones', N'U') IS NULL
BEGIN
    CREATE TABLE etl.revisiones (
        id_revision   INT IDENTITY(1,1) CONSTRAINT PK_Etl_Revisiones PRIMARY KEY,
        id_caso       BIGINT NULL           -- excepción de tipo "Revisión de Extracción"
            CONSTRAINT FK_Etl_Revisiones_Casos REFERENCES core.casos_tgr (id_caso),
        id_resultado  BIGINT NULL           -- excepción de tipo "Rechazo del ETL"
            CONSTRAINT FK_Etl_Revisiones_Resultados REFERENCES etl.resultados (id_resultado),
        estado        NVARCHAR(20) NOT NULL
            CONSTRAINT CK_Etl_Revisiones_estado CHECK (estado IN (N'Pendiente', N'Resuelto Manual', N'Descartado')),
        observacion   NVARCHAR(1000) NOT NULL,
        cambios       NVARCHAR(MAX) NULL,   -- JSON: {campo: {antes, despues}} de los datos corregidos
        id_caso_nuevo BIGINT NULL           -- caso creado al corregir y cargar una fila rechazada
            CONSTRAINT FK_Etl_Revisiones_Caso_Nuevo REFERENCES core.casos_tgr (id_caso),
        id_usuario    INT NOT NULL
            CONSTRAINT FK_Etl_Revisiones_Usuarios REFERENCES dbo.Usuarios (id_usuario),
        fecha         DATETIME2(0) NOT NULL CONSTRAINT DF_Etl_Revisiones_fecha DEFAULT (SYSDATETIME()),
        CONSTRAINT CK_Etl_Revisiones_origen CHECK (   -- exactamente uno de los dos
            (id_caso IS NOT NULL AND id_resultado IS NULL) OR (id_caso IS NULL AND id_resultado IS NOT NULL))
    );
    CREATE INDEX IX_Etl_Revisiones_caso ON etl.revisiones (id_caso, id_revision);
    CREATE INDEX IX_Etl_Revisiones_resultado ON etl.revisiones (id_resultado, id_revision);
END;
GO
