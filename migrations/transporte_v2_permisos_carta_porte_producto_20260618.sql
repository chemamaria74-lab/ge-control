-- Alcance configurable de PermSCT/NumPermisoSCT para Carta Porte 3.1.
-- SAT CartaPorte31.xsd exige ambos atributos en Autotransporte; el XSD no
-- contiene una matriz producto-permiso, por lo que esta relacion es control
-- de cumplimiento administrado por la empresa.

alter table if exists public.tr_permisos_operacion
  add column if not exists nombre_interno text not null default '',
  add column if not exists numero_permiso text not null default '',
  add column if not exists categoria_producto text not null default '',
  add column if not exists familias_producto jsonb not null default '[]'::jsonb,
  add column if not exists productos_permitidos jsonb not null default '[]'::jsonb,
  add column if not exists vehiculo_ids jsonb not null default '[]'::jsonb;

create index if not exists idx_tr_permisos_producto_activo
  on public.tr_permisos_operacion(user_id, perfil_id, activo, tipo_permiso);

comment on column public.tr_permisos_operacion.familias_producto is
  'Alcance administrativo: gas_lp, petroliferos, gasolinas, magna, premium, diesel u otros.';
comment on column public.tr_permisos_operacion.productos_permitidos is
  'IDs o claves de productos especificos cubiertos; se combina como union con familias_producto.';
comment on column public.tr_permisos_operacion.vehiculo_ids is
  'Unidades autorizadas para usar este PermSCT/NumPermisoSCT; vacio significa cualquier unidad del transportista.';
