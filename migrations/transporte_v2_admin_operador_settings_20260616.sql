alter table if exists public.tr_proveedores_operacion
  add column if not exists tipo text not null default 'Proveedor',
  add column if not exists producto text not null default '',
  add column if not exists permiso_cre text not null default '',
  add column if not exists permiso_almacenamiento_terminal text not null default '';

create index if not exists idx_tr_proveedores_operacion_producto
  on public.tr_proveedores_operacion(user_id, perfil_id, producto, activo);

alter table if exists public.tr_settings
  add column if not exists perfil_id bigint,
  add column if not exists data jsonb not null default '{}'::jsonb;

create index if not exists idx_tr_settings_user_perfil
  on public.tr_settings(user_id, perfil_id);

alter table if exists public.tr_operador_accesos
  add column if not exists usuario text,
  add column if not exists pin_hash text,
  add column if not exists vehiculo_id bigint,
  add column if not exists updated_at timestamptz;

create index if not exists idx_tr_operador_accesos_usuario_perfil
  on public.tr_operador_accesos(perfil_id, usuario, status);
