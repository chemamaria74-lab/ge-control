-- GE Control - Gas LP invoice email delivery
-- Adds customer billing email and invoice email delivery metadata.

begin;

alter table if exists public.gas_lp_clientes_facturacion
  add column if not exists email text not null default '';

alter table if exists public.gas_lp_clientes_facturacion
  add column if not exists email_facturacion text not null default '';

alter table if exists public.gas_lp_facturas
  add column if not exists email_enviado boolean not null default false;

alter table if exists public.gas_lp_facturas
  add column if not exists email_enviado_at timestamptz;

alter table if exists public.gas_lp_facturas
  add column if not exists email_destinatario text not null default '';

alter table if exists public.gas_lp_facturas
  add column if not exists email_error text not null default '';

create index if not exists idx_gas_lp_clientes_facturacion_email
  on public.gas_lp_clientes_facturacion(user_id, perfil_id, tenant_id, email);

commit;
