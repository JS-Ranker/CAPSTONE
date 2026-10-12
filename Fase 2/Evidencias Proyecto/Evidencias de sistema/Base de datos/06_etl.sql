/* =============================================================
   TTDH Automation - 06. Seguimiento del ETL en Python (RF02, RF05, RF10)
   Registra cada ejecución del ETL (CSV TGR -> stg.casos_tgr -> core.casos_tgr) y el resultado
   de cada fila: cargada, rechazada (con su motivo) o descartada por duplicada.
   No modifica stg.casos_tgr ni core.casos_tgr (creacion_db.sql, recepcion_datos_input.sql y
   creacion_tablas.sql): solo agrega tablas en el esquema etl.
   Se puede ejecutar más de una vez y no borra datos. Ejecutar después de esos tres scripts y de 04.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 06_etl.sql
   ============================================================= */

USE TTDH_Automation;
GO

IF SCHEMA_ID(N'etl') IS NULL
    EXEC(N'CREATE SCHEMA etl');
GO

-- Una fila por ejecución: qué archivo se procesó y cuántas filas terminaron en cada resultado.
IF OBJECT_ID(N'etl.ejecuciones', N'U') IS NULL
    CREATE TABLE etl.ejecuciones (
        id_ejecucion   INT IDENTITY(1,1) CONSTRAINT PK_Etl_Ejecuciones PRIMARY KEY,
        id_archivo     INT NULL          -- documento recibido (nulo si el CSV no pasó por la recepción)
            CONSTRAINT FK_Etl_Ejecuciones_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
        archivo_origen NVARCHAR(500) NOT NULL,
        fecha_inicio   DATETIME2(0)  NOT NULL CONSTRAINT DF_Etl_Ejecuciones_fecha DEFAULT (SYSDATETIME()),
        filas_leidas   INT NOT NULL CONSTRAINT DF_Etl_Ejecuciones_leidas DEFAULT (0),
        cargadas       INT NOT NULL CONSTRAINT DF_Etl_Ejecuciones_cargadas DEFAULT (0),
        rechazadas     INT NOT NULL CONSTRAINT DF_Etl_Ejecuciones_rechazadas DEFAULT (0),
        duplicadas     INT NOT NULL CONSTRAINT DF_Etl_Ejecuciones_duplicadas DEFAULT (0)
    );
GO

-- Una fila por cada fila del CSV: enlaza el dato original (stg) con el caso cargado (core).
-- Los rechazados quedan con su motivo: son la base de la Bandeja de Excepciones (RF05).
IF OBJECT_ID(N'etl.resultados', N'U') IS NULL
BEGIN
    CREATE TABLE etl.resultados (
        id_resultado BIGINT IDENTITY(1,1) CONSTRAINT PK_Etl_Resultados PRIMARY KEY,
        id_ejecucion INT    NOT NULL
            CONSTRAINT FK_Etl_Resultados_Ejecuciones REFERENCES etl.ejecuciones (id_ejecucion),
        id_stg       BIGINT NOT NULL
            CONSTRAINT FK_Etl_Resultados_Stg REFERENCES stg.casos_tgr (id_stg)
            CONSTRAINT UQ_Etl_Resultados_stg UNIQUE,
        resultado    NVARCHAR(20) NOT NULL
            CONSTRAINT CK_Etl_Resultados_resultado CHECK (resultado IN (N'Cargado', N'Rechazado', N'Duplicado')),
        motivo       NVARCHAR(300) NULL,  -- por qué se rechazó o de qué caso es duplicado
        id_caso      BIGINT NULL           -- caso creado (Cargado) o el que ya existía (Duplicado)
            CONSTRAINT FK_Etl_Resultados_Casos REFERENCES core.casos_tgr (id_caso),
        CONSTRAINT CK_Etl_Resultados_caso CHECK (resultado = N'Rechazado' OR id_caso IS NOT NULL)
    );
    CREATE INDEX IX_Etl_Resultados_ejecucion ON etl.resultados (id_ejecucion, resultado);
    CREATE INDEX IX_Etl_Resultados_caso ON etl.resultados (id_caso);
END;
GO
