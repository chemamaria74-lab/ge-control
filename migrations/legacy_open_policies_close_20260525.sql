-- Cierre controlado de policies legacy abiertas.
-- Objetivo: eliminar USING true / WITH CHECK true en tablas Gas LP legacy
-- sin tocar datos ni cambiar estructura funcional.
--
-- Aplicar despues de desplegar el backend que usa Supabase service role/JWT
-- para estas rutas. Reversibilidad operativa: si se necesita auditar primero,
-- ejecutar en la misma sesion:
--   select set_config('app.ge_drop_legacy_open_policies', 'false', false);

do $$
declare
  should_drop boolean;
begin
  should_drop := coalesce(current_setting('app.ge_drop_legacy_open_policies', true), 'true') <> 'false';

  if should_drop then
    drop policy if exists backend_full_access_providers on public.providers;
    drop policy if exists backend_full_access_records on public.records;
    drop policy if exists backend_full_access_reports on public.reports;
    drop policy if exists backend_full_access_facilities on public.user_facilities;
    drop policy if exists backend_full_access_settings on public.zc_settings;
    drop policy if exists backend_full_access_audit on public.settings_audit;
    drop policy if exists audit_insert_system on public.settings_audit;
  end if;
end $$;

alter table if exists public.providers enable row level security;
alter table if exists public.records enable row level security;
alter table if exists public.reports enable row level security;
alter table if exists public.user_facilities enable row level security;
alter table if exists public.zc_settings enable row level security;
alter table if exists public.settings_audit enable row level security;

-- Policies autenticadas explicitas. Service role mantiene bypass RLS por Supabase.
drop policy if exists ge_providers_own_rows on public.providers;
create policy ge_providers_own_rows on public.providers
  for all to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

drop policy if exists ge_records_own_rows on public.records;
create policy ge_records_own_rows on public.records
  for all to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

drop policy if exists ge_reports_own_rows on public.reports;
create policy ge_reports_own_rows on public.reports
  for all to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

drop policy if exists ge_user_facilities_own_rows on public.user_facilities;
create policy ge_user_facilities_own_rows on public.user_facilities
  for all to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

drop policy if exists ge_zc_settings_own_rows on public.zc_settings;
create policy ge_zc_settings_own_rows on public.zc_settings
  for all to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

drop policy if exists ge_settings_audit_read_own on public.settings_audit;
create policy ge_settings_audit_read_own on public.settings_audit
  for select to authenticated
  using (user_id = auth.uid()::text);

drop policy if exists ge_settings_audit_insert_own on public.settings_audit;
create policy ge_settings_audit_insert_own on public.settings_audit
  for insert to authenticated
  with check (user_id = auth.uid()::text);

do $$
begin
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='providers' and column_name='perfil_id') then
    create index if not exists idx_providers_user_perfil on public.providers(user_id, perfil_id);
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='records' and column_name='perfil_id') then
    create index if not exists idx_records_user_perfil_periodo_tipo on public.records(user_id, perfil_id, periodo, tipo);
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='reports' and column_name='perfil_id') then
    create index if not exists idx_reports_user_perfil_periodo on public.reports(user_id, perfil_id, periodo);
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='user_facilities' and column_name='perfil_id') then
    create index if not exists idx_user_facilities_user_perfil on public.user_facilities(user_id, perfil_id);
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='zc_settings' and column_name='perfil_id') then
    create index if not exists idx_zc_settings_user_perfil on public.zc_settings(user_id, perfil_id);
  end if;
  if exists (select 1 from information_schema.columns where table_schema='public' and table_name='settings_audit' and column_name='user_id')
     and exists (select 1 from information_schema.columns where table_schema='public' and table_name='settings_audit' and column_name='created_at') then
    create index if not exists idx_settings_audit_user_created on public.settings_audit(user_id, created_at);
  end if;
end $$;
