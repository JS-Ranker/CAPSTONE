/* =============================================================
   TTDH Automation - 04. Recepción multicanal (RF01, CU02)
   Agrega a Archivos_TGR los datos que exige RF01 y la huella del archivo
   para rechazar documentos ya recibidos (RN02, CU02 4a).
   Se puede ejecutar más de una vez y no borra datos. Ejecutar después de 02 y 03.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 04_recepcion.sql
   ============================================================= */

USE TTDH_Automation;
GO

-- Requerido por el índice filtrado (sqlcmd lo deja desactivado por defecto).
SET QUOTED_IDENTIFIER ON;
GO

-- Asunto y fecha del correo de origen (RF01: trazabilidad del correo). Nulos en SFTP y Web.
IF COL_LENGTH(N'dbo.Archivos_TGR', N'asunto_correo') IS NULL
    ALTER TABLE dbo.Archivos_TGR ADD asunto_correo NVARCHAR(255) NULL;
IF COL_LENGTH(N'dbo.Archivos_TGR', N'fecha_correo') IS NULL
    ALTER TABLE dbo.Archivos_TGR ADD fecha_correo DATETIME2(0) NULL;

-- Huella SHA-256 del contenido: el mismo documento no se registra dos veces,
-- aunque llegue con otro nombre o por otro canal (RN02, CU02 4a).
IF COL_LENGTH(N'dbo.Archivos_TGR', N'hash_sha256') IS NULL
    ALTER TABLE dbo.Archivos_TGR ADD hash_sha256 CHAR(64) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_Archivos_correo')
    ALTER TABLE dbo.Archivos_TGR ADD CONSTRAINT CK_Archivos_correo
        CHECK (canal_origen = N'Correo' OR (asunto_correo IS NULL AND fecha_correo IS NULL));

-- Índice único filtrado: permite filas antiguas sin huella y evita duplicados aunque dos cargas
-- del mismo archivo lleguen al mismo tiempo.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_Archivos_hash' AND object_id = OBJECT_ID(N'dbo.Archivos_TGR'))
    CREATE UNIQUE INDEX UX_Archivos_hash ON dbo.Archivos_TGR (hash_sha256) WHERE hash_sha256 IS NOT NULL;

-- Lotes recientes (CU02 paso 7) y documentos pendientes de extracción.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Archivos_estado_fecha' AND object_id = OBJECT_ID(N'dbo.Archivos_TGR'))
    CREATE INDEX IX_Archivos_estado_fecha ON dbo.Archivos_TGR (estado_archivo, fecha_recepcion);
GO
