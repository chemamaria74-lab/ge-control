-- GE Control - Gas LP Excel facility import metadata
-- Safe additive migration. It does not delete or rewrite existing facilities.

begin;

alter table public.user_facilities
  add column if not exists updated_at timestamptz,
  add column if not exists import_source text,
  add column if not exists import_source_file text,
  add column if not exists import_source_hash text,
  add column if not exists import_batch_id text,
  add column if not exists import_payload jsonb not null default '{}'::jsonb;

create index if not exists idx_user_facilities_scope_permiso
  on public.user_facilities(user_id, perfil_id, num_permiso);

create index if not exists idx_user_facilities_scope_clave
  on public.user_facilities(user_id, perfil_id, clave_instalacion);

create index if not exists idx_user_facilities_import_hash
  on public.user_facilities(user_id, perfil_id, import_source_hash);

commit;
