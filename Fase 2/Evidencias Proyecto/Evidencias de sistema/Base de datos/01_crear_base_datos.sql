/* =============================================================
   TTDH Automation - 01. Creación de la base de datos
   Motor: Microsoft SQL Server 2019 o superior (Developer / Express)
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 01_crear_base_datos.sql
   ============================================================= */

IF DB_ID(N'TTDH_Automation') IS NULL
BEGIN
    CREATE DATABASE TTDH_Automation COLLATE Modern_Spanish_CI_AS;
END
GO
