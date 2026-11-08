/* =============================================================
   TTDH Automation - 11. Revisión de informes con error de extracción (RF05, RN05, CU05, CU12 5b)
   Cuando un informe no se puede usar tal cual (por ejemplo, la suma de los montos leídos no coincide con el
   total que declara el documento), la extracción guarda lo que alcanzó a leer para que el analista lo corrija
   en la Bandeja de Excepciones y lo envíe al ETL.
   - etl.extracciones:          cabecera de lo extraído (totales declarados, errores y observaciones).
   - etl.extraccion_filas:      una fila por deudor leído, con su confianza por columna (JSON).
   - etl.revisiones_documento:  historial de revisiones del informe (se agrega una fila por acción).
   No modifica las tablas existentes. Se puede ejecutar más de una vez y no borra datos.
   Ejecutar después de 07_revisiones.sql: sqlcmd -S localhost -E -C -f 65001 -i 11_extraccion_revision.sql
   ============================================================= */

USE TTDH_Automation;
GO

IF OBJECT_ID(N'etl.extracciones', N'U') IS NULL
    CREATE TABLE etl.extracciones (
        id_archivo        INT NOT NULL CONSTRAINT PK_Etl_Extracciones PRIMARY KEY
            CONSTRAINT FK_Etl_Extracciones_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
        lote              NVARCHAR(100) NULL,
        fecha_documento   NVARCHAR(30) NULL,
        cantidad_declarada INT NULL,
        suma_declarada    BIGINT NULL,
        errores           NVARCHAR(MAX) NOT NULL,   -- JSON: lista de textos
        observaciones     NVARCHAR(MAX) NOT NULL,   -- JSON: lista de textos
        fecha             DATETIME2(0) NOT NULL CONSTRAINT DF_Etl_Extracciones_fecha DEFAULT (SYSDATETIME())
    );
GO

IF OBJECT_ID(N'etl.extraccion_filas', N'U') IS NULL
BEGIN
    CREATE TABLE etl.extraccion_filas (
        id_fila    BIGINT IDENTITY(1,1) CONSTRAINT PK_Etl_Extraccion_Filas PRIMARY KEY,
        id_archivo INT NOT NULL
            CONSTRAINT FK_Etl_Extraccion_Filas_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
        orden      INT NOT NULL,                    -- posición en el documento, desde 1
        valores    NVARCHAR(MAX) NOT NULL,          -- JSON: {columna: texto leído}
        confianzas NVARCHAR(MAX) NOT NULL           -- JSON: {columna: 0-100}
    );
    CREATE UNIQUE INDEX UX_Etl_Extraccion_Filas ON etl.extraccion_filas (id_archivo, orden);
END;
GO

IF OBJECT_ID(N'etl.revisiones_documento', N'U') IS NULL
BEGIN
    CREATE TABLE etl.revisiones_documento (
        id_revision INT IDENTITY(1,1) CONSTRAINT PK_Etl_Revisiones_Documento PRIMARY KEY,
        id_archivo  INT NOT NULL
            CONSTRAINT FK_Etl_Revisiones_Documento_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
        estado      NVARCHAR(20) NOT NULL
            CONSTRAINT CK_Etl_Revisiones_Documento_estado CHECK (estado IN (N'Pendiente', N'Resuelto Manual', N'Descartado')),
        observacion NVARCHAR(1000) NOT NULL,
        cambios     NVARCHAR(MAX) NULL,             -- JSON: {descripción: {antes, despues}} de lo corregido
        id_usuario  INT NOT NULL
            CONSTRAINT FK_Etl_Revisiones_Documento_Usuarios REFERENCES dbo.Usuarios (id_usuario),
        fecha       DATETIME2(0) NOT NULL CONSTRAINT DF_Etl_Revisiones_Documento_fecha DEFAULT (SYSDATETIME())
    );
    CREATE INDEX IX_Etl_Revisiones_Documento ON etl.revisiones_documento (id_archivo, id_revision);
END;
GO
