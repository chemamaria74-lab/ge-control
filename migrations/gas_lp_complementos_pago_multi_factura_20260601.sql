create table if not exists public.gas_lp_complementos_pago (
  id bigserial primary key,
  factura_id bigint not null references public.gas_lp_facturas(id) on delete cascade,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  uuid_sat text not null default '',
  xml_content text not null default '',
  status text not null default 'timbrado',
  fecha_pago timestamptz,
  forma_pago text not null default '03',
  monto numeric(14,2) not null default 0,
  saldo_insoluto numeric(14,2) not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gas_lp_complementos_pago_facturas (
  id bigserial primary key,
  complemento_id bigint references public.gas_lp_complementos_pago(id) on delete cascade,
  factura_id bigint not null references public.gas_lp_facturas(id) on delete cascade,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  uuid_relacionado text not null default '',
  monto numeric(14,2) not null default 0,
  saldo_anterior numeric(14,2) not null default 0,
  saldo_insoluto numeric(14,2) not null default 0,
  status text not null default 'timbrado',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (complemento_id, factura_id)
);

create index if not exists idx_glp_complementos_pago_scope
  on public.gas_lp_complementos_pago (user_id, tenant_id, perfil_id, created_at desc);

create index if not exists idx_glp_complementos_pago_facturas_factura
  on public.gas_lp_complementos_pago_facturas (factura_id, created_at desc);

alter table public.gas_lp_complementos_pago enable row level security;
alter table public.gas_lp_complementos_pago_facturas enable row level security;

revoke all on public.gas_lp_complementos_pago from anon, authenticated;
revoke all on public.gas_lp_complementos_pago_facturas from anon, authenticated;
