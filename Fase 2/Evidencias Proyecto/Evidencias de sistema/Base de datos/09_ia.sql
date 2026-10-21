/* =============================================================
   TTDH Automation - 09. Módulo de IA analítica (RF08, CU08)
   - ia.analisis: un análisis por informe recibido (después del ETL).
   - ia.insights: hallazgos del análisis (anomalías de casos, tendencias de rechazo, calidad del documento),
     con nivel Alto/Medio/Bajo, sugerencia y estado de su revisión (CU08 pasos 4 y 4a).
   - ia.reglas: validaciones sugeridas por la IA que el analista aplicó; el ETL las usa en los procesos
     siguientes (CU08 paso 5).
   La tabla dbo.Analisis_IA_Anomalias (02_tablas.sql) era del modelo anterior (cuelga de Conciliacion_Banco)
   y no se usa. Este script no la modifica.
   Se puede ejecutar más de una vez y no borra datos. Ejecutar después de 06_etl.sql.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 09_ia.sql
   ============================================================= */

USE TTDH_Automation;
GO

IF SCHEMA_ID(N'ia') IS NULL
    EXEC(N'CREATE SCHEMA ia');
GO

IF OBJECT_ID(N'ia.analisis', N'U') IS NULL
    CREATE TABLE ia.analisis (
        id_analisis      INT IDENTITY(1,1) CONSTRAINT PK_Ia_Analisis PRIMARY KEY,
        id_archivo       INT NOT NULL
            CONSTRAINT FK_Ia_Analisis_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
        fecha            DATETIME2(0) NOT NULL CONSTRAINT DF_Ia_Analisis_fecha DEFAULT (SYSDATETIME()),
        modelo           NVARCHAR(100) NOT NULL,     -- p. ej. "IsolationForest (scikit-learn 1.5)"
        casos_analizados INT NOT NULL,
        casos_historial  INT NOT NULL,               -- casos con que se entrenó el modelo
        resumen          NVARCHAR(1000) NOT NULL
    );
GO

IF OBJECT_ID(N'ia.insights', N'U') IS NULL
BEGIN
    CREATE TABLE ia.insights (
        id_insight      INT IDENTITY(1,1) CONSTRAINT PK_Ia_Insights PRIMARY KEY,
        id_analisis     INT NOT NULL
            CONSTRAINT FK_Ia_Insights_Analisis REFERENCES ia.analisis (id_analisis),
        tipo            NVARCHAR(30) NOT NULL
            CONSTRAINT CK_Ia_Insights_tipo CHECK (tipo IN (N'Anomalía de caso', N'Tendencia de rechazo',
                                                         N'Calidad del documento')),
        nivel           NVARCHAR(10) NOT NULL
            CONSTRAINT CK_Ia_Insights_nivel CHECK (nivel IN (N'Alto', N'Medio', N'Bajo')),
        titulo          NVARCHAR(200) NOT NULL,
        detalle         NVARCHAR(2000) NOT NULL,     -- por qué: los rasgos que la hacen anómala
        sugerencia      NVARCHAR(500) NULL,
        regla_sugerida  NVARCHAR(400) NULL,          -- JSON de la validación que se puede aplicar
        id_caso         BIGINT NULL
            CONSTRAINT FK_Ia_Insights_Casos REFERENCES core.casos_tgr (id_caso),
        puntaje         DECIMAL(9,4) NULL,           -- puntaje de anomalía del modelo (mayor = más anómalo)
        estado          NVARCHAR(20) NOT NULL CONSTRAINT DF_Ia_Insights_estado DEFAULT (N'Pendiente')
            CONSTRAINT CK_Ia_Insights_estado CHECK (estado IN (N'Pendiente', N'Aplicada', N'Revisada')),
        observacion     NVARCHAR(1000) NULL,
        id_usuario      INT NULL
            CONSTRAINT FK_Ia_Insights_Usuarios REFERENCES dbo.Usuarios (id_usuario),
        fecha_revision  DATETIME2(0) NULL
    );
    CREATE INDEX IX_Ia_Insights_analisis ON ia.insights (id_analisis, nivel);
    CREATE INDEX IX_Ia_Insights_estado ON ia.insights (estado, nivel);
END;
GO

IF OBJECT_ID(N'ia.reglas', N'U') IS NULL
    CREATE TABLE ia.reglas (
        id_regla    INT IDENTITY(1,1) CONSTRAINT PK_Ia_Reglas PRIMARY KEY,
        tipo        NVARCHAR(30) NOT NULL
            CONSTRAINT CK_Ia_Reglas_tipo CHECK (tipo IN (N'monto_maximo')),
        valor       DECIMAL(19,2) NOT NULL,
        descripcion NVARCHAR(300) NOT NULL,
        id_insight  INT NOT NULL CONSTRAINT FK_Ia_Reglas_Insights REFERENCES ia.insights (id_insight),
        activa      BIT NOT NULL CONSTRAINT DF_Ia_Reglas_activa DEFAULT (1),
        fecha       DATETIME2(0) NOT NULL CONSTRAINT DF_Ia_Reglas_fecha DEFAULT (SYSDATETIME())
    );
GO
