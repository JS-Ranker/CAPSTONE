
USE TTDH_Automation;
GO

IF OBJECT_ID(N'stg.casos_tgr', N'U') IS NULL
BEGIN
    CREATE TABLE stg.casos_tgr (

        -- Identificador interno
        id_stg BIGINT IDENTITY(1,1) PRIMARY KEY,

        -- Datos originales provenientes del CSV
        nombre_documento NVARCHAR(255),
        rut NVARCHAR(30),
        dv NVARCHAR(5),
        id_demanda NVARCHAR(100),
        n_resol NVARCHAR(100),
        nom_cli NVARCHAR(300),
        monto_solicitado NVARCHAR(60),
        saldo_menor_05_utm NVARCHAR(100),
        tipo_embargo NVARCHAR(150),
        rol NVARCHAR(250),
        fec_ing NVARCHAR(80),
        tesoreria NVARCHAR(250),
        fecha_oficio NVARCHAR(80),
        mult_rol NVARCHAR(30),
        rev_manual NVARCHAR(30),
        camp_falt NVARCHAR(MAX),
        ent_banco NVARCHAR(250),
        id_correo NVARCHAR(500),
        remit NVARCHAR(320),
        asunto NVARCHAR(1000),
        ruta_doc NVARCHAR(2048),

        -- Control de carga
        fecha_carga_utc DATETIME2(0)
            NOT NULL DEFAULT SYSUTCDATETIME(),

        archivo_origen NVARCHAR(500) NULL
    );
END;
GO
