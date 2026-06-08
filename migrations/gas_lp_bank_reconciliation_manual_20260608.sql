create table if not exists public.gas_lp_invoice_bank_reconciliations (
  id bigserial primary key,
  factura_id bigint not null references public.gas_lp_facturas(id) on delete cascade,
  user_id uuid,
  tenant_id uuid,
  perfil_id bigint,
  amount numeric(14,2) not null default 0,
  difference numeric(14,2) not null default 0,
  status text not null default 'pendiente',
  payment_detected_at timestamptz,
  confirmed_by text,
  confirmed_by_name text,
  confirmed_at timestamptz,
  reference_note text not null default '',
  comment text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint gas_lp_invoice_bank_reconciliations_status_chk check (
    status in ('pendiente','conciliada','parcial','diferencia','no_identificada','reversada')
  ),
  constraint gas_lp_invoice_bank_reconciliations_factura_unique unique (factura_id)
);

create table if not exists public.gas_lp_bank_reconciliation_audit_logs (
  id bigserial primary key,
  reconciliation_id bigint references public.gas_lp_invoice_bank_reconciliations(id) on delete set null,
  factura_id bigint not null references public.gas_lp_facturas(id) on delete cascade,
  user_id uuid,
  tenant_id uuid,
  perfil_id bigint,
  action text not null default '',
  old_status text,
  new_status text not null default '',
  actor_user_id text,
  actor_name text,
  comment text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_glp_bank_reconciliations_scope
  on public.gas_lp_invoice_bank_reconciliations (user_id, tenant_id, perfil_id, status, updated_at desc);

create index if not exists idx_glp_bank_reconciliations_factura
  on public.gas_lp_invoice_bank_reconciliations (factura_id);

create index if not exists idx_glp_bank_reconciliation_audit_factura
  on public.gas_lp_bank_reconciliation_audit_logs (factura_id, created_at desc);

alter table public.gas_lp_invoice_bank_reconciliations enable row level security;
alter table public.gas_lp_bank_reconciliation_audit_logs enable row level security;

revoke all on public.gas_lp_invoice_bank_reconciliations from anon, authenticated;
revoke all on public.gas_lp_bank_reconciliation_audit_logs from anon, authenticated;
