create table if not exists public.saas_billing_invoices (
  id bigserial primary key,
  tenant_id uuid,
  customer_name text not null,
  customer_rfc text not null,
  customer_cp text not null,
  customer_regimen text not null,
  uso_cfdi text not null default 'G03',
  concept text not null default 'Servicio de uso/licencia plataforma GE Control',
  subtotal numeric(18, 2) not null default 0,
  iva numeric(18, 2) not null default 0,
  retencion_iva numeric(18, 2) not null default 0,
  retencion_isr numeric(18, 2) not null default 0,
  total numeric(18, 2) not null default 0,
  status text not null default 'borrador' check (status in ('borrador', 'timbrada', 'cancelada', 'error')),
  uuid_sat text,
  xml_content text,
  pdf_storage_bucket text,
  pdf_storage_path text,
  xml_storage_bucket text,
  xml_storage_path text,
  error_message text,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  stamped_at timestamptz
);

create index if not exists idx_saas_billing_invoices_tenant
  on public.saas_billing_invoices (tenant_id, created_at desc);

create index if not exists idx_saas_billing_invoices_status
  on public.saas_billing_invoices (status, created_at desc);

alter table public.saas_billing_invoices enable row level security;

comment on table public.saas_billing_invoices is
  'Superadmin billing invoices for GE Control SaaS/RESICO. Access through backend superadmin APIs only.';

create table if not exists public.saas_billing_settings (
  id integer primary key default 1 check (id = 1),
  rfc text,
  fiscal_name text,
  fiscal_cp text,
  fiscal_regimen text not null default '626',
  default_concept text not null default 'Servicio de uso/licencia plataforma GE Control',
  default_price numeric(18, 2) not null default 0,
  updated_by uuid,
  updated_at timestamptz not null default now()
);

alter table public.saas_billing_settings enable row level security;

comment on table public.saas_billing_settings is
  'Non-secret GE Control fiscal billing settings editable by Superadmin. Secrets stay in Render ENV.';
