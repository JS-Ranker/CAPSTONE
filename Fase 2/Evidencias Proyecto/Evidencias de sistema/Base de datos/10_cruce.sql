/* =============================================================
   TTDH Automation - 10. Cruce con Banco Genérico (RF04)
   - banco.cuentas: simula el core bancario de Banco Genérico (cuentas y saldos por RUT). El cruce solo la lee:
     el cargo real lo hace el core. Se llena con backend/scripts/cargar_core_bancario.py.
   - cruce.utm: valor de la UTM de cada mes, que actualiza el analista (no va fijo en el código).
   - cruce.ejecuciones / cruce.resultados / cruce.descuentos: cada cruce de un informe, el resultado de cada caso
     con su motivo y de qué cuenta sale cada descuento. Volver a cruzar un informe crea una ejecución nueva; la
     vigente es la última.
   Llena core.casos_tgr.saldo_menor_05_utm ("SI"/"NO"; nulo si no es cliente), la columna del modelo de Tomás.
   Se puede ejecutar más de una vez y no borra datos. Ejecutar después de 06_etl.sql.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 10_cruce.sql
   ============================================================= */

USE TTDH_Automation;
GO

IF SCHEMA_ID(N'banco') IS NULL
    EXEC(N'CREATE SCHEMA banco');
GO
IF SCHEMA_ID(N'cruce') IS NULL
    EXEC(N'CREATE SCHEMA cruce');
GO

IF OBJECT_ID(N'banco.cuentas', N'U') IS NULL
BEGIN
    CREATE TABLE banco.cuentas (
        id_cuenta     INT IDENTITY(1,1) CONSTRAINT PK_Banco_Cuentas PRIMARY KEY,
        rut           VARCHAR(9)    NOT NULL,          -- sin puntos ni DV, como core.casos_tgr.rut_limpio
        dv            CHAR(1)       NOT NULL,
        numero_cuenta NVARCHAR(20)  NOT NULL CONSTRAINT UQ_Banco_Cuentas_numero UNIQUE,
        tipo_cuenta   NVARCHAR(25)  NOT NULL
            CONSTRAINT CK_Banco_Cuentas_tipo CHECK (tipo_cuenta IN
                (N'Cuenta RUT', N'Cuenta corriente', N'Chequera electrónica', N'Cuenta de ahorro')),
        saldo         DECIMAL(19,2) NOT NULL CONSTRAINT CK_Banco_Cuentas_saldo CHECK (saldo >= 0),
        estado        NVARCHAR(10)  NOT NULL
            CONSTRAINT CK_Banco_Cuentas_estado CHECK (estado IN (N'Activa', N'Bloqueada', N'Cerrada'))
    );
    CREATE INDEX IX_Banco_Cuentas_rut ON banco.cuentas (rut, estado);
END;
GO

IF OBJECT_ID(N'cruce.utm', N'U') IS NULL
    CREATE TABLE cruce.utm (
        periodo     CHAR(7)       NOT NULL CONSTRAINT PK_Cruce_Utm PRIMARY KEY      -- 'AAAA-MM'
            CONSTRAINT CK_Cruce_Utm_periodo CHECK (periodo LIKE '[2][0-9][0-9][0-9]-[01][0-9]'),
        valor       DECIMAL(12,2) NOT NULL CONSTRAINT CK_Cruce_Utm_valor CHECK (valor > 0),
        id_usuario  INT NULL CONSTRAINT FK_Cruce_Utm_Usuarios REFERENCES dbo.Usuarios (id_usuario),
        fecha       DATETIME2(0)  NOT NULL CONSTRAINT DF_Cruce_Utm_fecha DEFAULT (SYSDATETIME())
    );
GO

IF OBJECT_ID(N'cruce.ejecuciones', N'U') IS NULL
BEGIN
    CREATE TABLE cruce.ejecuciones (
        id_ejecucion      INT IDENTITY(1,1) CONSTRAINT PK_Cruce_Ejecuciones PRIMARY KEY,
        id_archivo        INT NOT NULL
            CONSTRAINT FK_Cruce_Ejecuciones_Archivos REFERENCES dbo.Archivos_TGR (id_archivo),
        periodo           CHAR(7)       NOT NULL,       -- mes de recepción del informe
        valor_utm         DECIMAL(12,2) NOT NULL,       -- la UTM usada (queda fija aunque luego se corrija)
        fecha             DATETIME2(0)  NOT NULL CONSTRAINT DF_Cruce_Ejecuciones_fecha DEFAULT (SYSDATETIME()),
        casos             INT NOT NULL,
        clientes          INT NOT NULL,                 -- casos cuyo RUT es cliente de Banco Genérico
        descontados       INT NOT NULL,
        parciales         INT NOT NULL,
        no_descontados    INT NOT NULL,
        en_revision       INT NOT NULL,
        monto_solicitado  DECIMAL(19,2) NOT NULL,
        monto_descontado  DECIMAL(19,2) NOT NULL
    );
    CREATE INDEX IX_Cruce_Ejecuciones_archivo ON cruce.ejecuciones (id_archivo, id_ejecucion);
END;
GO

IF OBJECT_ID(N'cruce.resultados', N'U') IS NULL
BEGIN
    CREATE TABLE cruce.resultados (
        id_resultado     BIGINT IDENTITY(1,1) CONSTRAINT PK_Cruce_Resultados PRIMARY KEY,
        id_ejecucion     INT    NOT NULL
            CONSTRAINT FK_Cruce_Resultados_Ejecuciones REFERENCES cruce.ejecuciones (id_ejecucion),
        id_caso          BIGINT NOT NULL
            CONSTRAINT FK_Cruce_Resultados_Casos REFERENCES core.casos_tgr (id_caso),
        resultado        NVARCHAR(20) NOT NULL
            CONSTRAINT CK_Cruce_Resultados_resultado CHECK (resultado IN
                (N'Descontado', N'Descontado parcial', N'No descontado', N'En revisión')),
        cliente          BIT NOT NULL,
        saldo_total      DECIMAL(19,2) NOT NULL,       -- suma de las cuentas activas al momento del cruce
        monto_solicitado DECIMAL(19,2) NULL,
        monto_descontado DECIMAL(19,2) NOT NULL,
        monto_pendiente  DECIMAL(19,2) NOT NULL,
        motivo           NVARCHAR(300) NOT NULL,
        CONSTRAINT UQ_Cruce_Resultados_caso UNIQUE (id_ejecucion, id_caso)
    );
    CREATE INDEX IX_Cruce_Resultados_caso ON cruce.resultados (id_caso);
END;
GO

IF OBJECT_ID(N'cruce.descuentos', N'U') IS NULL
    CREATE TABLE cruce.descuentos (
        id_descuento  BIGINT IDENTITY(1,1) CONSTRAINT PK_Cruce_Descuentos PRIMARY KEY,
        id_resultado  BIGINT NOT NULL
            CONSTRAINT FK_Cruce_Descuentos_Resultados REFERENCES cruce.resultados (id_resultado),
        id_cuenta     INT NOT NULL
            CONSTRAINT FK_Cruce_Descuentos_Cuentas REFERENCES banco.cuentas (id_cuenta),
        monto         DECIMAL(19,2) NOT NULL CONSTRAINT CK_Cruce_Descuentos_monto CHECK (monto > 0)
    );
GO
