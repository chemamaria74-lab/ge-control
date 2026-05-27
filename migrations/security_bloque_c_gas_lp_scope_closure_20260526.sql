-- Bloque C - Cierre de seguridad Gas LP.
-- Objetivo:
-- 1) Archivar filas operativas ambiguas con perfil_id IS NULL.
-- 2) Cerrar policies legacy abiertas.
-- 3) Exigir alcance por perfil en tablas criticas Gas LP.
--
-- Nota: service_role mantiene bypass RLS para backend. Esta migracion evita que
-- clientes authenticated lean/escriban filas sin perfil y conserva evidencia de
-- las filas archivadas en public.security_profile_null_archive.

begin;

create table if not exists public.security_profile_null_archive (
  id bigserial primary key,
  table_name text not null,
  row_pk text not null,
  user_id text,
  tenant_id text,
  perfil_id text,
  archived_at timestamptz not null default now(),
  reason text not null default 'perfil_id_null_bloque_c',
  payload jsonb not null
);

alter table public.security_profile_null_archive enable row level security;

drop policy if exists ge_security_profile_null_archive_backend_only_select on public.security_profile_null_archive;
create policy ge_security_profile_null_archive_backend_only_select
on public.security_profile_null_archive
for select to authenticated
using (false);

drop policy if exists ge_security_profile_null_archive_backend_only_insert on public.security_profile_null_archive;
create policy ge_security_profile_null_archive_backend_only_insert
on public.security_profile_null_archive
for insert to authenticated
with check (false);

create unique index if not exists idx_security_profile_null_archive_unique
  on public.security_profile_null_archive(table_name, row_pk);

create or replace function public.ge_archive_profile_null_rows(
  p_table regclass,
  p_pk text default 'id',
  p_reason text default 'perfil_id_null_bloque_c'
) returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted_count integer := 0;
  table_text text := p_table::text;
begin
  if not exists (
    select 1
    from pg_attribute
    where attrelid = p_table
      and attname = 'perfil_id'
      and not attisdropped
  ) then
    return 0;
  end if;

  execute format(
    'insert into public.security_profile_null_archive(table_name,row_pk,user_id,tenant_id,perfil_id,reason,payload)
     select %L, to_jsonb(t)->>%L, to_jsonb(t)->>''user_id'', to_jsonb(t)->>''tenant_id'', to_jsonb(t)->>''perfil_id'', %L, to_jsonb(t)
     from %s t
     where perfil_id is null
     on conflict (table_name,row_pk) do nothing',
    table_text,
    p_pk,
    p_reason,
    p_table
  );
  get diagnostics inserted_count = row_count;

  execute format('delete from %s where perfil_id is null', p_table);

  return inserted_count;
end;
$$;

select public.ge_archive_profile_null_rows('public.providers'::regclass);
select public.ge_archive_profile_null_rows('public.records'::regclass);
select public.ge_archive_profile_null_rows('public.reports'::regclass);
select public.ge_archive_profile_null_rows('public.user_facilities'::regclass);
select public.ge_archive_profile_null_rows('public.zc_settings'::regclass);
select public.ge_archive_profile_null_rows('public.gas_lp_facturas'::regclass);
select public.ge_archive_profile_null_rows('public.gas_lp_facturas_servicio'::regclass);
select public.ge_archive_profile_null_rows('public.gas_lp_choferes'::regclass);
select public.ge_archive_profile_null_rows('public.gas_lp_vehiculos'::regclass);
select public.ge_archive_profile_null_rows('public.gas_lp_rutas'::regclass);
select public.ge_archive_profile_null_rows('public.gas_lp_clientes_facturacion'::regclass);

drop function if exists public.ge_archive_profile_null_rows(regclass, text, text);

drop policy if exists backend_full_access_providers on public.providers;
drop policy if exists backend_full_access_records on public.records;
drop policy if exists backend_full_access_reports on public.reports;
drop policy if exists backend_full_access_facilities on public.user_facilities;
drop policy if exists backend_full_access_settings on public.zc_settings;
drop policy if exists backend_full_access_audit on public.settings_audit;
drop policy if exists audit_insert_system on public.settings_audit;

alter table if exists public.providers enable row level security;
alter table if exists public.records enable row level security;
alter table if exists public.reports enable row level security;
alter table if exists public.user_facilities enable row level security;
alter table if exists public.zc_settings enable row level security;
alter table if exists public.gas_lp_facturas enable row level security;
alter table if exists public.gas_lp_facturas_servicio enable row level security;
alter table if exists public.gas_lp_choferes enable row level security;
alter table if exists public.gas_lp_vehiculos enable row level security;
alter table if exists public.gas_lp_rutas enable row level security;
alter table if exists public.gas_lp_clientes_facturacion enable row level security;

drop policy if exists ge_providers_own_rows on public.providers;
create policy ge_providers_own_rows on public.providers
for all to authenticated
using (
  user_id = auth.uid()::text
  and perfil_id is not null
  and exists (
    select 1 from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section = 'gas_lp'
      and us.perfil_id = providers.perfil_id
  )
)
with check (user_id = auth.uid()::text and perfil_id is not null);

drop policy if exists ge_records_own_rows on public.records;
create policy ge_records_own_rows on public.records
for all to authenticated
using (
  user_id = auth.uid()::text
  and perfil_id is not null
  and exists (
    select 1 from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section = 'gas_lp'
      and us.perfil_id = records.perfil_id
  )
)
with check (user_id = auth.uid()::text and perfil_id is not null);

drop policy if exists ge_reports_own_rows on public.reports;
create policy ge_reports_own_rows on public.reports
for all to authenticated
using (
  user_id = auth.uid()::text
  and perfil_id is not null
  and exists (
    select 1 from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section = 'gas_lp'
      and us.perfil_id = reports.perfil_id
  )
)
with check (user_id = auth.uid()::text and perfil_id is not null);

drop policy if exists ge_user_facilities_own_rows on public.user_facilities;
create policy ge_user_facilities_own_rows on public.user_facilities
for all to authenticated
using (
  user_id = auth.uid()::text
  and perfil_id is not null
  and exists (
    select 1 from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section = coalesce(user_facilities.modulo_propietario, 'gas_lp')
      and us.perfil_id = user_facilities.perfil_id
  )
)
with check (user_id = auth.uid()::text and perfil_id is not null);

drop policy if exists ge_zc_settings_own_rows on public.zc_settings;
create policy ge_zc_settings_own_rows on public.zc_settings
for all to authenticated
using (
  user_id = auth.uid()::text
  and perfil_id is not null
  and exists (
    select 1 from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section = 'gas_lp'
      and us.perfil_id = zc_settings.perfil_id
  )
)
with check (user_id = auth.uid()::text and perfil_id is not null);

drop policy if exists ge_gas_lp_facturas_own_rows on public.gas_lp_facturas;
create policy ge_gas_lp_facturas_own_rows on public.gas_lp_facturas
for all to authenticated
using (user_id = auth.uid() and perfil_id is not null and exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_facturas.perfil_id
))
with check (user_id = auth.uid() and perfil_id is not null);

drop policy if exists ge_gas_lp_facturas_servicio_own_rows on public.gas_lp_facturas_servicio;
create policy ge_gas_lp_facturas_servicio_own_rows on public.gas_lp_facturas_servicio
for all to authenticated
using (user_id = auth.uid() and perfil_id is not null and exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_facturas_servicio.perfil_id
))
with check (user_id = auth.uid() and perfil_id is not null);

drop policy if exists ge_gas_lp_choferes_own_rows on public.gas_lp_choferes;
create policy ge_gas_lp_choferes_own_rows on public.gas_lp_choferes
for all to authenticated
using (user_id = auth.uid() and perfil_id is not null and exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_choferes.perfil_id
))
with check (user_id = auth.uid() and perfil_id is not null);

drop policy if exists ge_gas_lp_vehiculos_own_rows on public.gas_lp_vehiculos;
create policy ge_gas_lp_vehiculos_own_rows on public.gas_lp_vehiculos
for all to authenticated
using (user_id = auth.uid() and perfil_id is not null and exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_vehiculos.perfil_id
))
with check (user_id = auth.uid() and perfil_id is not null);

drop policy if exists ge_gas_lp_rutas_own_rows on public.gas_lp_rutas;
create policy ge_gas_lp_rutas_own_rows on public.gas_lp_rutas
for all to authenticated
using (user_id = auth.uid() and perfil_id is not null and exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_rutas.perfil_id
))
with check (user_id = auth.uid() and perfil_id is not null);

drop policy if exists ge_gas_lp_clientes_own_rows on public.gas_lp_clientes_facturacion;
create policy ge_gas_lp_clientes_own_rows on public.gas_lp_clientes_facturacion
for all to authenticated
using (user_id = auth.uid() and perfil_id is not null and exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_clientes_facturacion.perfil_id
))
with check (user_id = auth.uid() and perfil_id is not null);

create index if not exists idx_security_profile_null_archive_table
  on public.security_profile_null_archive(table_name, archived_at desc);

commit;
