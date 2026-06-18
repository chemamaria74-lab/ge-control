update public.tr_origenes
set
  tipo_carta_porte = coalesce(nullif(tipo_carta_porte, ''), 'Origen'),
  permiso_cre = coalesce(nullif(permiso_cre, ''), metadata ->> 'permiso_cre'),
  clave_instalacion = coalesce(nullif(clave_instalacion, ''), metadata ->> 'clave_instalacion'),
  id_ubicacion_carta_porte = coalesce(nullif(id_ubicacion_carta_porte, ''), metadata ->> 'id_ubicacion_carta_porte', 'OR' || lpad(id::text, 6, '0')),
  estado_sat = coalesce(nullif(estado_sat, ''), metadata ->> 'estado_sat'),
  municipio_sat = coalesce(nullif(municipio_sat, ''), metadata ->> 'municipio_sat'),
  localidad_sat = coalesce(nullif(localidad_sat, ''), metadata ->> 'localidad_sat')
where true;

update public.tr_destinos
set
  tipo_carta_porte = coalesce(nullif(tipo_carta_porte, ''), 'Destino'),
  permiso_cre = coalesce(nullif(permiso_cre, ''), metadata ->> 'permiso_cre'),
  clave_instalacion = coalesce(nullif(clave_instalacion, ''), metadata ->> 'clave_instalacion'),
  id_ubicacion_carta_porte = coalesce(nullif(id_ubicacion_carta_porte, ''), metadata ->> 'id_ubicacion_carta_porte', 'DE' || lpad(id::text, 6, '0')),
  estado_sat = coalesce(nullif(estado_sat, ''), metadata ->> 'estado_sat'),
  municipio_sat = coalesce(nullif(municipio_sat, ''), metadata ->> 'municipio_sat'),
  localidad_sat = coalesce(nullif(localidad_sat, ''), metadata ->> 'localidad_sat')
where true;
