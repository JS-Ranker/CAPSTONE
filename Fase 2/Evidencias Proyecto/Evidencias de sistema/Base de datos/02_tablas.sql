/* =============================================================
   TTDH Automation - 02. Tablas, llaves y restricciones
   Basado en el Modelo Entidad-Relación (Modelos de Datos y Arquitectura).
   ATENCIÓN: recrea las tablas desde cero (borra los datos existentes).
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 02_tablas.sql
   ============================================================= */

USE TTDH_Automation;
GO

-- Se eliminan en orden inverso a las dependencias.
DROP TABLE IF EXISTS dbo.Bitacora_Trazabilidad;
DROP TABLE IF EXISTS dbo.Analisis_IA_Anomalias;
DROP TABLE IF EXISTS dbo.Conciliacion_Banco;
DROP TABLE IF EXISTS dbo.Registros_TGR;
DROP TABLE IF EXISTS dbo.Archivos_TGR;
DROP TABLE IF EXISTS dbo.Usuarios;
DROP TABLE IF EXISTS dbo.Roles;
GO

/* ---------------------------------------------------------- Seguridad (RF09) */
CREATE TABLE dbo.Roles (
    id_rol        INT IDENTITY(1,1) CONSTRAINT PK_Roles PRIMARY KEY,
    nombre_rol    NVARCHAR(50)  NOT NULL CONSTRAINT UQ_Roles_nombre UNIQUE,
    descripcion   NVARCHAR(255) NULL
);

CREATE TABLE dbo.Usuarios (
    id_usuario      INT IDENTITY(1,1) CONSTRAINT PK_Usuarios PRIMARY KEY,
    id_rol          INT NOT NULL CONSTRAINT FK_Usuarios_Roles REFERENCES dbo.Roles (id_rol),
    usuario_ad      NVARCHAR(100) NOT NULL CONSTRAINT UQ_Usuarios_usuario_ad UNIQUE,
    nombre_completo NVARCHAR(150) NOT NULL,
    activo          BIT NOT NULL CONSTRAINT DF_Usuarios_activo DEFAULT (1)
);
GO

/* ---------------------------------------------------- Recepción (RF01, RF12) */
CREATE TABLE dbo.Archivos_TGR (
    id_archivo           INT IDENTITY(1,1) CONSTRAINT PK_Archivos_TGR PRIMARY KEY,
    nombre_archivo       NVARCHAR(255) NOT NULL,
    canal_origen         NVARCHAR(10)  NOT NULL
        CONSTRAINT CK_Archivos_canal CHECK (canal_origen IN (N'Correo', N'SFTP', N'Web')),
    remitente            NVARCHAR(255) NULL,          -- solo cuando el canal es Correo
    tipo_documento       NVARCHAR(20)  NOT NULL
        CONSTRAINT CK_Archivos_tipo CHECK (tipo_documento IN
            (N'Excel', N'CSV', N'TXT', N'PDF con texto', N'PDF escaneado', N'Imagen')),
    ruta_original        NVARCHAR(500) NOT NULL,
    fecha_recepcion      DATETIME2(0)  NOT NULL CONSTRAINT DF_Archivos_fecha DEFAULT (SYSDATETIME()),
    estado_archivo       NVARCHAR(30)  NOT NULL CONSTRAINT DF_Archivos_estado DEFAULT (N'Recibido')
        CONSTRAINT CK_Archivos_estado CHECK (estado_archivo IN
            (N'Recibido', N'Normalizado', N'Pendiente de Extracción', N'Error de Extracción', N'Procesado', N'Error')),
    total_registros      INT NULL CONSTRAINT CK_Archivos_total CHECK (total_registros >= 0),
    confianza_extraccion DECIMAL(5,2) NULL             -- promedio OCR (0-100); nulo en formatos estructurados
        CONSTRAINT CK_Archivos_confianza CHECK (confianza_extraccion BETWEEN 0 AND 100),
    CONSTRAINT CK_Archivos_remitente CHECK (canal_origen = N'Correo' OR remitente IS NULL)
);

/* ------------------------------------------------ Registros TGR (RF02, RF03) */
CREATE TABLE dbo.Registros_TGR (
    id_registro          INT IDENTITY(1,1) CONSTRAINT PK_Registros_TGR PRIMARY KEY,
    id_archivo           INT NOT NULL CONSTRAINT FK_Registros_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
    rut_deudor           NVARCHAR(12)  NULL,            -- formato 12345678-9; validado con Módulo 11 (RN01)
    folio_deuda          NVARCHAR(50)  NULL,
    monto_deuda          DECIMAL(18,2) NULL,
    fecha_origen         DATE          NULL,
    estado_validacion    NVARCHAR(30)  NOT NULL CONSTRAINT DF_Registros_estado DEFAULT (N'Válido')
        CONSTRAINT CK_Registros_estado CHECK (estado_validacion IN
            (N'Válido', N'Inválido', N'Duplicado', N'Revisión de Extracción')),
    confianza_extraccion DECIMAL(5,2) NULL              -- confianza OCR del registro (RN05)
        CONSTRAINT CK_Registros_confianza CHECK (confianza_extraccion BETWEEN 0 AND 100)
);
CREATE INDEX IX_Registros_archivo ON dbo.Registros_TGR (id_archivo);
CREATE INDEX IX_Registros_rut     ON dbo.Registros_TGR (rut_deudor);

/* --------------------------------------------- Conciliación (RF04, RF05) */
CREATE TABLE dbo.Conciliacion_Banco (
    id_conciliacion     INT IDENTITY(1,1) CONSTRAINT PK_Conciliacion_Banco PRIMARY KEY,
    id_registro         INT NOT NULL
        CONSTRAINT FK_Conciliacion_Registros REFERENCES dbo.Registros_TGR (id_registro)
        CONSTRAINT UQ_Conciliacion_registro UNIQUE,     -- relación 1 a 0..1
    cuenta_bancaria     NVARCHAR(30)  NULL,
    estado_conciliacion NVARCHAR(20)  NOT NULL CONSTRAINT DF_Conciliacion_estado DEFAULT (N'Pendiente')
        CONSTRAINT CK_Conciliacion_estado CHECK (estado_conciliacion IN
            (N'Conciliado', N'Rechazado Banco', N'Pendiente')),
    detalle_observacion NVARCHAR(MAX) NULL,
    fecha_cruce         DATETIME2(0)  NOT NULL CONSTRAINT DF_Conciliacion_fecha DEFAULT (SYSDATETIME())
);

/* ------------------------------------------------------------ IA (RF08) */
CREATE TABLE dbo.Analisis_IA_Anomalias (
    id_analisis     INT IDENTITY(1,1) CONSTRAINT PK_Analisis_IA PRIMARY KEY,
    id_conciliacion INT NOT NULL CONSTRAINT FK_Analisis_Conciliacion REFERENCES dbo.Conciliacion_Banco (id_conciliacion),
    nivel_anomalia  NVARCHAR(10)  NOT NULL
        CONSTRAINT CK_Analisis_nivel CHECK (nivel_anomalia IN (N'Bajo', N'Medio', N'Alto')),
    sugerencia_ia   NVARCHAR(MAX) NULL,
    fecha_analisis  DATETIME2(0)  NOT NULL CONSTRAINT DF_Analisis_fecha DEFAULT (SYSDATETIME())
);
CREATE INDEX IX_Analisis_conciliacion ON dbo.Analisis_IA_Anomalias (id_conciliacion);

/* ------------------------------------------------- Auditoría (RF10) */
CREATE TABLE dbo.Bitacora_Trazabilidad (
    id_bitacora      INT IDENTITY(1,1) CONSTRAINT PK_Bitacora PRIMARY KEY,
    id_usuario       INT NOT NULL CONSTRAINT FK_Bitacora_Usuarios REFERENCES dbo.Usuarios (id_usuario),
    accion_ejecutada NVARCHAR(100) NOT NULL,
    timestamp_accion DATETIME2(0)  NOT NULL CONSTRAINT DF_Bitacora_fecha DEFAULT (SYSDATETIME()),
    detalle_cambio   NVARCHAR(MAX) NULL
);
CREATE INDEX IX_Bitacora_usuario ON dbo.Bitacora_Trazabilidad (id_usuario, timestamp_accion);
GO

-- RF10: la bitácora es inalterable; no se permite modificar ni borrar registros.
CREATE TRIGGER dbo.TR_Bitacora_Inalterable
ON dbo.Bitacora_Trazabilidad
INSTEAD OF UPDATE, DELETE
AS
BEGIN
    THROW 50001, N'La Bitácora de Trazabilidad es inalterable (RF10): no se permite modificar ni eliminar registros.', 1;
END
GO
