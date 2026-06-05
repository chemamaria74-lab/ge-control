alter table if exists public.gas_lp_complementos_pago
  add column if not exists email_enviado boolean not null default false,
  add column if not exists email_enviado_at timestamptz,
  add column if not exists email_destinatario text not null default '',
  add column if not exists email_error text not null default '',
  add column if not exists email_last_attempt_at timestamptz,
  add column if not exists email_delivery jsonb not null default '{}'::jsonb;

create index if not exists idx_glp_complementos_pago_email
  on public.gas_lp_complementos_pago (tenant_id, perfil_id, email_enviado, created_at desc);
