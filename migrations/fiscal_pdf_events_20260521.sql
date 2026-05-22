create table if not exists public.fiscal_document_events (
  id bigserial primary key,
  tenant_id uuid,
  user_id uuid,
  perfil_id integer,
  module text not null,
  entity_type text not null,
  entity_id text not null,
  uuid_sat text,
  action text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_fiscal_document_events_scope
  on public.fiscal_document_events (module, entity_type, entity_id, created_at desc);

create index if not exists idx_fiscal_document_events_user
  on public.fiscal_document_events (user_id, perfil_id, created_at desc);

alter table public.fiscal_document_events enable row level security;

comment on table public.fiscal_document_events is
  'Best-effort audit for GE Control fiscal XML/PDF generation, storage and download events.';
