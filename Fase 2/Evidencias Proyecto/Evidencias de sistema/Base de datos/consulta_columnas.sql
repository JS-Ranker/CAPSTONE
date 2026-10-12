SELECT
    id_caso,
	nombre_documento,
    rut_limpio,
    dv_limpio,
    nom_cli,
    id_demanda,
    n_resol,
    monto_solicitado,
    rol_cod,
    rol_anio,
    rol_loc,
    tesoreria_tipo,
    tesoreria_loc,
    CONVERT(VARCHAR(10), fec_ing, 105) AS fec_ing,
    CONVERT(VARCHAR(10), fecha_oficio, 105) AS fecha_oficio,
    mult_rol_bit,
    rev_manual_bit,
	ruta_doc
FROM core.casos_tgr
ORDER BY id_caso;