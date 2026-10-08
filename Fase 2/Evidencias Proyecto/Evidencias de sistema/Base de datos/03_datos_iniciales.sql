/* =============================================================
   TTDH Automation - 03. Datos iniciales
   Roles de la plataforma (RF09) y un usuario del sistema para la bitácora.
   Ejecutar desde la carpeta "Base de datos": sqlcmd -S localhost -E -C -f 65001 -i 03_datos_iniciales.sql
   ============================================================= */

USE TTDH_Automation;
GO

MERGE dbo.Roles AS destino
USING (VALUES
    (N'Administrador',            N'Administra usuarios, roles y configuración de la plataforma.'),
    (N'Analista de Conciliación', N'Carga documentos, revisa excepciones y ejecuta los procesos de cruce.'),
    (N'Auditor',                  N'Consulta la bitácora de auditoría y la trazabilidad de los procesos.'),
    (N'Consulta',                 N'Visualiza el dashboard y los reportes, sin modificar información.')
) AS origen (nombre_rol, descripcion)
ON destino.nombre_rol = origen.nombre_rol
WHEN NOT MATCHED THEN
    INSERT (nombre_rol, descripcion) VALUES (origen.nombre_rol, origen.descripcion);
GO

-- Usuario técnico que registra en la bitácora las acciones de los procesos automáticos.
IF NOT EXISTS (SELECT 1 FROM dbo.Usuarios WHERE usuario_ad = N'sistema.ttdh')
    INSERT INTO dbo.Usuarios (id_rol, usuario_ad, nombre_completo, activo)
    SELECT id_rol, N'sistema.ttdh', N'Proceso automático TTDH', 1
    FROM dbo.Roles WHERE nombre_rol = N'Administrador';
GO
