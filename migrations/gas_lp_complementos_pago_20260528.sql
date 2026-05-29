create table if not exists public.gas_lp_complementos_pago (
  id bigserial primary key,
  factura_id bigint not null references public.gas_lp_facturas(id) on delete cascade,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  uuid_sat text not null default '',
  xml_content text not null default '',
  pdf_url text not null default '',
  status text not null default 'timbrado',
  fecha_pago timestamptz not null,
  forma_pago text not null default '03',
  moneda text not null default 'MXN',
  monto numeric(14, 2) not null default 0,
  saldo_anterior numeric(14, 2) not null default 0,
  saldo_insoluto numeric(14, 2) not null default 0,
  parcialidad integer not null default 1,
  created_by_internal bigint,
  created_by_internal_name text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_gas_lp_complementos_factura
  on public.gas_lp_complementos_pago (factura_id, created_at desc);

create index if not exists idx_gas_lp_complementos_scope
  on public.gas_lp_complementos_pago (user_id, tenant_id, perfil_id, created_at desc);
