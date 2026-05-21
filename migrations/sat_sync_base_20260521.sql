-- SAT Sync / Cargas Detectadas base architecture.
-- Staging-safe: creates metadata tables only; it does not mutate existing CFDI,
-- Carta Porte or monthly export data.

create extension if not exists pgcrypto;

create table if not exists public.sat_credentials (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  company_id uuid not null,
  rfc text not null,
  auth_type text not null check (auth_type in ('ciec', 'efirma', 'provider_api')),
  provider_api text,
  encrypted_credentials jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  last_successful_sync_at timestamptz,
  last_error text,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.sat_sync_jobs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  company_id uuid not null,
  status text not null default 'pending'
    check (status in ('pending', 'running', 'completed', 'failed')),
  sync_type text not null default 'both'
    check (sync_type in ('received', 'issued', 'both')),
  date_from timestamptz not null,
  date_to timestamptz not null,
  provider text not null default 'sw_sapiens'
    check (provider in ('sw_sapiens', 'sat_ws', 'facturapi', 'manual')),
  external_request_id text,
  started_at timestamptz,
  finished_at timestamptz,
  error_message text,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.cfdi_sat_inbox (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  company_id uuid not null,
  uuid text not null,
  tipo text not null check (tipo in ('ingreso', 'egreso', 'traslado', 'pago')),
  rfc_emisor text,
  nombre_emisor text,
  rfc_receptor text,
  nombre_receptor text,
  fecha timestamptz,
  total numeric(18, 6),
  moneda text,
  metodo_pago text,
  forma_pago text,
  uso_cfdi text,
  xml_url text,
  raw_xml text,
  parsed_json jsonb not null default '{}'::jsonb,
  source text not null default 'sat_sync',
  detected_at timestamptz not null default now(),
  processed_status text not null default 'new'
    check (processed_status in ('new', 'ignored', 'load_draft_created', 'carta_porte_created')),
  created_at timestamptz not null default now(),
  unique (uuid)
);

create table if not exists public.detected_loads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  company_id uuid not null,
  cfdi_id uuid references public.cfdi_sat_inbox(id) on delete cascade,
  proveedor_id uuid,
  cliente_id uuid,
  producto_detectado text,
  litros_detectados numeric(18, 6),
  unidad_detectada text,
  origen_detectado text,
  destino_detectado text,
  fecha_detectada timestamptz,
  confidence_score numeric(5, 2) not null default 0,
  status text not null default 'pending_confirmation'
    check (status in ('pending_confirmation', 'confirmed', 'rejected', 'carta_porte_created')),
  assigned_operator_id uuid,
  confirmed_by uuid,
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_sat_credentials_scope on public.sat_credentials (tenant_id, company_id, rfc, active);
create index if not exists idx_sat_sync_jobs_scope_status on public.sat_sync_jobs (tenant_id, company_id, status, created_at desc);
create index if not exists idx_cfdi_sat_inbox_scope_fecha on public.cfdi_sat_inbox (tenant_id, company_id, fecha desc);
create index if not exists idx_cfdi_sat_inbox_processed on public.cfdi_sat_inbox (processed_status, detected_at desc);
create index if not exists idx_detected_loads_scope_status on public.detected_loads (tenant_id, company_id, status, created_at desc);

alter table public.sat_credentials enable row level security;
alter table public.sat_sync_jobs enable row level security;
alter table public.cfdi_sat_inbox enable row level security;
alter table public.detected_loads enable row level security;

-- The backend service role bypasses RLS. Browser clients must use backend APIs;
-- direct anon/authenticated access is intentionally not granted in this base migration.

comment on table public.sat_credentials is 'Encrypted SAT/PAC credential metadata per tenant/company. Never store CIEC/e.firma in plaintext.';
comment on table public.sat_sync_jobs is 'SAT/PAC sync worker runs with overlap windows and retry/error metadata.';
comment on table public.cfdi_sat_inbox is 'Deduplicated CFDI inbox by UUID for issued/received XML discovered by SAT Sync.';
comment on table public.detected_loads is 'Operational load drafts detected from CFDI XML and awaiting operator confirmation.';
