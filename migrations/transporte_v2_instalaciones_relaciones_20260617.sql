alter table if exists public.tr_origenes
  add column if not exists proveedor_id bigint,
  add column if not exists proveedor_nombre text,
  add column if not exists cliente_id bigint,
  add column if not exists cliente_nombre text;

alter table if exists public.tr_destinos
  add column if not exists proveedor_id bigint,
  add column if not exists proveedor_nombre text,
  add column if not exists cliente_nombre text;

create index if not exists idx_tr_origenes_proveedor_perfil
  on public.tr_origenes(user_id, perfil_id, proveedor_id, activo);

create index if not exists idx_tr_destinos_cliente_perfil
  on public.tr_destinos(user_id, perfil_id, cliente_id, activo);
