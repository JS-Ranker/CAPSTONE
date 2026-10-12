/* =============================================================
   TTDH Automation - 08. Informes de deudores en Word (RF01)
   La TGR puede enviar el informe en Word (.docx): se agrega 'Word' a los tipos de Archivos_TGR.
   Solo amplía la lista de valores permitidos (los datos existentes siguen cumpliéndola).
   Se puede ejecutar más de una vez y no borra datos.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 08_word.sql
   ============================================================= */

USE TTDH_Automation;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_Archivos_tipo' AND definition LIKE N'%Word%'
)
BEGIN
    BEGIN TRANSACTION;
    ALTER TABLE dbo.Archivos_TGR DROP CONSTRAINT CK_Archivos_tipo;
    ALTER TABLE dbo.Archivos_TGR ADD CONSTRAINT CK_Archivos_tipo CHECK (tipo_documento IN
        (N'Excel', N'CSV', N'TXT', N'Word', N'PDF con texto', N'PDF escaneado', N'Imagen'));
    COMMIT TRANSACTION;
END;
GO
