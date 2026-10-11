/* =============================================================
   TTDH Automation - 05. Remitentes autorizados (RF01, CU02 paso 2)
   Lista de correos de la TGR cuyos adjuntos se aceptan. Se administra desde la pantalla de ingesta
   (antes se definía en REMITENTES_AUTORIZADOS del .env del backend).
   Un remitente quitado se desactiva, no se borra: queda el historial de quién estuvo autorizado.
   Se puede ejecutar más de una vez y no borra datos. Ejecutar después de 04.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 05_remitentes.sql
   ============================================================= */

USE TTDH_Automation;
GO

SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.Remitentes_Autorizados', N'U') IS NULL
    CREATE TABLE dbo.Remitentes_Autorizados (
        id_remitente   INT IDENTITY(1,1) CONSTRAINT PK_Remitentes PRIMARY KEY,
        correo         NVARCHAR(255) NOT NULL CONSTRAINT UQ_Remitentes_correo UNIQUE,  -- siempre en minúsculas
        nombre         NVARCHAR(150) NULL,                                              -- p. ej. "TGR - Nóminas"
        activo         BIT           NOT NULL CONSTRAINT DF_Remitentes_activo DEFAULT (1),
        fecha_creacion DATETIME2(0)  NOT NULL CONSTRAINT DF_Remitentes_fecha DEFAULT (SYSDATETIME()),
        CONSTRAINT CK_Remitentes_minusculas CHECK (correo = LOWER(correo) COLLATE Latin1_General_BIN2),
        CONSTRAINT CK_Remitentes_formato CHECK (correo LIKE N'_%@_%._%')
    );
GO
