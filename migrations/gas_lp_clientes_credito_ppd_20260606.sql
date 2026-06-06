alter table if exists public.gas_lp_clientes_facturacion
  add column if not exists credito_habilitado boolean not null default false,
  add column if not exists dias_credito integer not null default 0,
  add column if not exists limite_credito numeric,
  add column if not exists credito_notas text not null default '',
  add column if not exists credito_actualizado_at timestamptz,
  add column if not exists credito_actualizado_por text;

create index if not exists idx_gas_lp_clientes_credito
  on public.gas_lp_clientes_facturacion(user_id, tenant_id, perfil_id, credito_habilitado, activo);
