
USE TTDH_Automation;
GO

IF OBJECT_ID(N'core.casos_tgr', N'U') IS NULL
BEGIN
    CREATE TABLE core.casos_tgr (

        -- Identificador interno
        id_caso BIGINT IDENTITY(1,1) PRIMARY KEY,

        -- Identificación del cliente
        rut_limpio VARCHAR(9) NOT NULL,
        dv_limpio CHAR(1) NOT NULL,
        nom_cli NVARCHAR(250),

        -- Identificación del documento
        nombre_documento NVARCHAR(255),
        id_demanda NVARCHAR(50),
        n_resol NVARCHAR(50),

        -- Información del embargo
        monto_solicitado DECIMAL(19,2),
        saldo_menor_05_utm NVARCHAR(30),
        est_ret NVARCHAR(50),

        -- Rol normalizado
        rol NVARCHAR(200) NOT NULL,
        rol_cod VARCHAR(30),
        rol_anio SMALLINT,
        rol_loc NVARCHAR(150),

        -- Fechas
        fec_ing DATE NOT NULL,
        fecha_oficio DATE,

        -- Tesorería normalizada
        tesoreria NVARCHAR(200),
        tesoreria_tipo VARCHAR(15),
        tesoreria_loc NVARCHAR(150),

        -- Indicadores
        mult_rol_bit BIT,
        rev_manual_bit BIT,
        camp_falt NVARCHAR(500),

        -- Información bancaria
        ent_banco NVARCHAR(150),

        -- Información de correo
        id_correo NVARCHAR(255),
        remit NVARCHAR(255),
        asunto NVARCHAR(500),

        -- Documentación
        ruta_doc NVARCHAR(1024),

        -- Control de carga
        fecha_carga_utc DATETIME2(0)
            DEFAULT SYSUTCDATETIME(),

        fecha_actualizacion_utc DATETIME2(0)
            DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Índice para los cruces posteriores
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_Casos_Llave'
      AND object_id = OBJECT_ID('core.casos_tgr')
)
BEGIN
    CREATE INDEX IX_Casos_Llave
    ON core.casos_tgr (
        rut_limpio,
        dv_limpio,
        rol,
        fec_ing
    );
END;
GO
