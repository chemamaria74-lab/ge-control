-- GE Control - Superadmin billing catalogs and safe cancellation metadata
-- Additive only. Does not change existing invoices or secrets.

begin;

alter table public.saas_billing_settings
  add column if not exists frequent_customers jsonb not null default '[]'::jsonb,
  add column if not exists default_concepts jsonb not null default '[]'::jsonb,
  add column if not exists fiscal_configs jsonb not null default '[]'::jsonb;

alter table public.saas_billing_invoices
  add column if not exists cancel_reason text,
  add column if not exists cancel_substitution_uuid text,
  add column if not exists cancel_ack text,
  add column if not exists canceled_at timestamptz,
  add column if not exists canceled_by uuid;

create index if not exists idx_saas_billing_invoices_cancel_status
  on public.saas_billing_invoices(status, canceled_at desc);

create unique index if not exists idx_invoice_cancellations_uuid_active
  on public.invoice_cancellations(uuid_sat)
  where status in ('pending', 'sent', 'ok', 'cancelled');

commit;
