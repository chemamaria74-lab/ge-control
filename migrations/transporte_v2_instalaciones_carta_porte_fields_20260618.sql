alter table public.tr_origenes
  add column if not exists tipo_carta_porte text,
  add column if not exists permiso_cre text,
  add column if not exists clave_instalacion text,
  add column if not exists id_ubicacion_carta_porte text,
  add column if not exists estado_sat text,
  add column if not exists municipio_sat text,
  add column if not exists localidad_sat text;

alter table public.tr_destinos
  add column if not exists tipo_carta_porte text,
  add column if not exists permiso_cre text,
  add column if not exists clave_instalacion text,
  add column if not exists id_ubicacion_carta_porte text,
  add column if not exists estado_sat text,
  add column if not exists municipio_sat text,
  add column if not exists localidad_sat text;

update public.tr_origenes
set tipo_carta_porte = 'Origen'
where tipo_carta_porte is null;

update public.tr_destinos
set tipo_carta_porte = 'Destino'
where tipo_carta_porte is null;
