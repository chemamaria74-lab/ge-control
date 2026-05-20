-- GE CONTROL - Arquitectura fiscal progresiva SAT/PAC/XML.
-- No destructiva: agrega tablas de auditoría y versionamiento para conectar
-- timbrado SW Sapiens / SW smarter sin romper flujos existentes.

create table if not exists public.sat_catalog_cache (
  id bigserial primary key,
  catalog_name text not null,
  catalog_key text not null,
  value jsonb not null default '{}'::jsonb,
  valid_from date,
  valid_to date,
  source_url text,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.pac_requests (
  id bigserial primary key,
  tenant_id uuid,
  user_id text,
  perfil_id bigint,
  module text not null check (module in ('transporte','gas_lp','gasolineras','admin_saas')),
  provider text not null default 'sw_sapien',
  environment text not null default 'sandbox',
  operation text not null,
  correlation_id text,
  request_hash text,
  request_payload jsonb,
  status text not null default 'pending',
  error_code text,
  error_message text,
  created_at timestamptz not null default now()
);

create table if not exists public.pac_responses (
  id bigserial primary key,
  request_id bigint references public.pac_requests(id) on delete set null,
  provider text not null default 'sw_sapien',
  http_status integer,
  response_payload jsonb,
  uuid_sat text,
  xml_original text,
  xml_timbrado text,
  pdf_url text,
  acuse_cancelacion text,
  status text not null default 'received',
  error_code text,
  error_message text,
  created_at timestamptz not null default now()
);

create table if not exists public.xml_versions (
  id bigserial primary key,
  tenant_id uuid,
  user_id text,
  perfil_id bigint,
  module text not null,
  entity_type text not null,
  entity_id text not null,
  uuid_sat text,
  version integer not null default 1,
  xml_kind text not null default 'timbrado',
  xml_content text,
  xml_hash text,
  source text not null default 'ge_control',
  created_by text,
  created_at timestamptz not null default now(),
  unique (module, entity_type, entity_id, version, xml_kind)
);

create table if not exists public.invoice_cancellations (
  id bigserial primary key,
  tenant_id uuid,
  user_id text,
  perfil_id bigint,
  module text not null,
  invoice_table text,
  invoice_id text,
  uuid_sat text not null,
  motivo text not null,
  uuid_sustitucion text,
  pac_request_id bigint references public.pac_requests(id) on delete set null,
  pac_response_id bigint references public.pac_responses(id) on delete set null,
  acuse_cancelacion text,
  status text not null default 'pending',
  requested_by text,
  requested_at timestamptz not null default now(),
  cancelled_at timestamptz
);

create index if not exists idx_pac_requests_scope
  on public.pac_requests(module, tenant_id, user_id, perfil_id, created_at desc);

create unique index if not exists idx_sat_catalog_cache_unique_period
  on public.sat_catalog_cache(catalog_name, catalog_key, coalesce(valid_from, date '1900-01-01'));

create index if not exists idx_pac_responses_uuid
  on public.pac_responses(uuid_sat);

create index if not exists idx_xml_versions_entity
  on public.xml_versions(module, entity_type, entity_id, created_at desc);

create index if not exists idx_invoice_cancellations_uuid
  on public.invoice_cancellations(uuid_sat, status);
