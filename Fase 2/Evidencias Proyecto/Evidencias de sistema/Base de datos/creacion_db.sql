USE master;
GO

-- Crear la base de datos si no existe
IF DB_ID(N'TTDH_Automation') IS NULL
BEGIN
    CREATE DATABASE TTDH_Automation;
END;
GO

-- Seleccionar la base de datos
USE TTDH_Automation;
GO

-- Crear esquemas
IF SCHEMA_ID('stg') IS NULL
    EXEC('CREATE SCHEMA stg');
GO

IF SCHEMA_ID('core') IS NULL
    EXEC('CREATE SCHEMA core');
GO

IF SCHEMA_ID('etl') IS NULL
    EXEC('CREATE SCHEMA etl');
GO
