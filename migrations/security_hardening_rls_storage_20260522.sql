-- GE Control security hardening - RLS, storage and scope indexes.
-- Safe/idempotent for staging: does not delete or mutate business rows.
-- Service role keeps backend access because Supabase bypasses RLS for service_role.

begin;

-- Keep false for this staging-safe run. Only set to true after moving legacy
-- Gas LP table access from anon get_supabase() to service role or user JWT.
select set_config('app.ge_drop_legacy_open_policies', 'false', true);

-- ---------------------------------------------------------------------------
-- 1) Critical tables: enable RLS and add explicit scoped/backend-only policies.
-- ---------------------------------------------------------------------------

alter table if exists public.tenants enable row level security;
alter table if exists public.companies enable row level security;
alter table if exists public.subscriptions enable row level security;
alter table if exists public.sat_credentials enable row level security;
alter table if exists public.sat_sync_jobs enable row level security;
alter table if exists public.cfdi_sat_inbox enable row level security;
alter table if exists public.detected_loads enable row level security;
alter table if exists public.fiscal_document_events enable row level security;
alter table if exists public.saas_billing_invoices enable row level security;
alter table if exists public.saas_billing_settings enable row level security;
alter table if exists public.tr_carta_aporte_tasks enable row level security;

-- Tenants: authenticated users can read only tenants attached to active modules.
drop policy if exists ge_tenants_member_select on public.tenants;
create policy ge_tenants_member_select
on public.tenants
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = tenants.id
  )
);

drop policy if exists ge_tenants_no_client_insert on public.tenants;
create policy ge_tenants_no_client_insert on public.tenants
for insert to authenticated
with check (false);

drop policy if exists ge_tenants_no_client_update on public.tenants;
create policy ge_tenants_no_client_update on public.tenants
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_tenants_no_client_delete on public.tenants;
create policy ge_tenants_no_client_delete on public.tenants
for delete to authenticated
using (false);

-- Companies/subscriptions: read only through active tenant membership.
drop policy if exists ge_companies_member_select on public.companies;
create policy ge_companies_member_select
on public.companies
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = companies.tenant_id
  )
);

drop policy if exists ge_companies_no_client_insert on public.companies;
create policy ge_companies_no_client_insert on public.companies
for insert to authenticated
with check (false);

drop policy if exists ge_companies_no_client_update on public.companies;
create policy ge_companies_no_client_update on public.companies
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_companies_no_client_delete on public.companies;
create policy ge_companies_no_client_delete on public.companies
for delete to authenticated
using (false);

drop policy if exists ge_subscriptions_member_select on public.subscriptions;
create policy ge_subscriptions_member_select
on public.subscriptions
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = subscriptions.tenant_id
  )
);

drop policy if exists ge_subscriptions_no_client_insert on public.subscriptions;
create policy ge_subscriptions_no_client_insert on public.subscriptions
for insert to authenticated
with check (false);

drop policy if exists ge_subscriptions_no_client_update on public.subscriptions;
create policy ge_subscriptions_no_client_update on public.subscriptions
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_subscriptions_no_client_delete on public.subscriptions;
create policy ge_subscriptions_no_client_delete on public.subscriptions
for delete to authenticated
using (false);

-- SAT credentials are always backend-only. Do not expose encrypted credential
-- payloads to browser clients even when scoped.
drop policy if exists ge_sat_credentials_backend_only_select on public.sat_credentials;
create policy ge_sat_credentials_backend_only_select on public.sat_credentials
for select to authenticated
using (false);

drop policy if exists ge_sat_credentials_backend_only_insert on public.sat_credentials;
create policy ge_sat_credentials_backend_only_insert on public.sat_credentials
for insert to authenticated
with check (false);

drop policy if exists ge_sat_credentials_backend_only_update on public.sat_credentials;
create policy ge_sat_credentials_backend_only_update on public.sat_credentials
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_sat_credentials_backend_only_delete on public.sat_credentials;
create policy ge_sat_credentials_backend_only_delete on public.sat_credentials
for delete to authenticated
using (false);

-- SAT jobs are backend-managed. Users can read scoped status, not write.
drop policy if exists ge_sat_sync_jobs_member_select on public.sat_sync_jobs;
create policy ge_sat_sync_jobs_member_select
on public.sat_sync_jobs
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = sat_sync_jobs.tenant_id
  )
);

drop policy if exists ge_sat_sync_jobs_no_client_insert on public.sat_sync_jobs;
create policy ge_sat_sync_jobs_no_client_insert on public.sat_sync_jobs
for insert to authenticated
with check (false);

drop policy if exists ge_sat_sync_jobs_no_client_update on public.sat_sync_jobs;
create policy ge_sat_sync_jobs_no_client_update on public.sat_sync_jobs
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_sat_sync_jobs_no_client_delete on public.sat_sync_jobs;
create policy ge_sat_sync_jobs_no_client_delete on public.sat_sync_jobs
for delete to authenticated
using (false);

-- CFDI inbox / detected loads / fiscal events: scoped read only.
drop policy if exists ge_cfdi_sat_inbox_member_select on public.cfdi_sat_inbox;
create policy ge_cfdi_sat_inbox_member_select
on public.cfdi_sat_inbox
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = cfdi_sat_inbox.tenant_id
      and (cfdi_sat_inbox.perfil_id is null or us.perfil_id = cfdi_sat_inbox.perfil_id)
  )
);

drop policy if exists ge_cfdi_sat_inbox_no_client_insert on public.cfdi_sat_inbox;
create policy ge_cfdi_sat_inbox_no_client_insert on public.cfdi_sat_inbox
for insert to authenticated
with check (false);

drop policy if exists ge_cfdi_sat_inbox_no_client_update on public.cfdi_sat_inbox;
create policy ge_cfdi_sat_inbox_no_client_update on public.cfdi_sat_inbox
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_cfdi_sat_inbox_no_client_delete on public.cfdi_sat_inbox;
create policy ge_cfdi_sat_inbox_no_client_delete on public.cfdi_sat_inbox
for delete to authenticated
using (false);

drop policy if exists ge_detected_loads_member_select on public.detected_loads;
create policy ge_detected_loads_member_select
on public.detected_loads
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = detected_loads.tenant_id
      and (detected_loads.perfil_id is null or us.perfil_id = detected_loads.perfil_id)
  )
);

drop policy if exists ge_detected_loads_no_client_insert on public.detected_loads;
create policy ge_detected_loads_no_client_insert on public.detected_loads
for insert to authenticated
with check (false);

drop policy if exists ge_detected_loads_no_client_update on public.detected_loads;
create policy ge_detected_loads_no_client_update on public.detected_loads
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_detected_loads_no_client_delete on public.detected_loads;
create policy ge_detected_loads_no_client_delete on public.detected_loads
for delete to authenticated
using (false);

drop policy if exists ge_fiscal_document_events_member_select on public.fiscal_document_events;
create policy ge_fiscal_document_events_member_select
on public.fiscal_document_events
for select
to authenticated
using (
  exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.tenant_id = fiscal_document_events.tenant_id
      and (fiscal_document_events.perfil_id is null or us.perfil_id = fiscal_document_events.perfil_id)
  )
);

drop policy if exists ge_fiscal_document_events_no_client_insert on public.fiscal_document_events;
create policy ge_fiscal_document_events_no_client_insert on public.fiscal_document_events
for insert to authenticated
with check (false);

drop policy if exists ge_fiscal_document_events_no_client_update on public.fiscal_document_events;
create policy ge_fiscal_document_events_no_client_update on public.fiscal_document_events
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_fiscal_document_events_no_client_delete on public.fiscal_document_events;
create policy ge_fiscal_document_events_no_client_delete on public.fiscal_document_events
for delete to authenticated
using (false);

-- Superadmin billing remains backend-only. Superadmin UI uses backend APIs.
drop policy if exists ge_saas_billing_invoices_backend_only_select on public.saas_billing_invoices;
create policy ge_saas_billing_invoices_backend_only_select on public.saas_billing_invoices
for select to authenticated
using (false);

drop policy if exists ge_saas_billing_invoices_backend_only_insert on public.saas_billing_invoices;
create policy ge_saas_billing_invoices_backend_only_insert on public.saas_billing_invoices
for insert to authenticated
with check (false);

drop policy if exists ge_saas_billing_invoices_backend_only_update on public.saas_billing_invoices;
create policy ge_saas_billing_invoices_backend_only_update on public.saas_billing_invoices
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_saas_billing_invoices_backend_only_delete on public.saas_billing_invoices;
create policy ge_saas_billing_invoices_backend_only_delete on public.saas_billing_invoices
for delete to authenticated
using (false);

drop policy if exists ge_saas_billing_settings_backend_only_select on public.saas_billing_settings;
create policy ge_saas_billing_settings_backend_only_select on public.saas_billing_settings
for select to authenticated
using (false);

drop policy if exists ge_saas_billing_settings_backend_only_insert on public.saas_billing_settings;
create policy ge_saas_billing_settings_backend_only_insert on public.saas_billing_settings
for insert to authenticated
with check (false);

drop policy if exists ge_saas_billing_settings_backend_only_update on public.saas_billing_settings;
create policy ge_saas_billing_settings_backend_only_update on public.saas_billing_settings
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_saas_billing_settings_backend_only_delete on public.saas_billing_settings;
create policy ge_saas_billing_settings_backend_only_delete on public.saas_billing_settings
for delete to authenticated
using (false);

-- Carta Aporte tasks: scoped direct read, backend writes.
drop policy if exists ge_tr_carta_aporte_tasks_member_select on public.tr_carta_aporte_tasks;
create policy ge_tr_carta_aporte_tasks_member_select
on public.tr_carta_aporte_tasks
for select
to authenticated
using (
  user_id = auth.uid()
  and exists (
    select 1
    from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section in ('transporte', 'gas_lp')
      and us.perfil_id = tr_carta_aporte_tasks.perfil_id
  )
);

drop policy if exists ge_tr_carta_aporte_tasks_no_client_insert on public.tr_carta_aporte_tasks;
create policy ge_tr_carta_aporte_tasks_no_client_insert on public.tr_carta_aporte_tasks
for insert to authenticated
with check (false);

drop policy if exists ge_tr_carta_aporte_tasks_no_client_update on public.tr_carta_aporte_tasks;
create policy ge_tr_carta_aporte_tasks_no_client_update on public.tr_carta_aporte_tasks
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_tr_carta_aporte_tasks_no_client_delete on public.tr_carta_aporte_tasks;
create policy ge_tr_carta_aporte_tasks_no_client_delete on public.tr_carta_aporte_tasks
for delete to authenticated
using (false);

-- ---------------------------------------------------------------------------
-- 2) Legacy open policies.
-- IMPORTANT: Gas LP legacy routes still use the backend anon Supabase client
-- with app-level user_id filters. Dropping these policies immediately can
-- break current Gas LP. The removal is therefore guarded by an explicit custom
-- setting and defaults to NO-OP.
--
-- To execute the legacy lock-down after moving those calls to service role or
-- user JWT, change the set_config near the top of this migration to 'true'.
-- ---------------------------------------------------------------------------

do $$
begin
  if coalesce(current_setting('app.ge_drop_legacy_open_policies', true), 'false') = 'true' then
    drop policy if exists backend_full_access_providers on public.providers;
    drop policy if exists backend_full_access_records on public.records;
    drop policy if exists backend_full_access_reports on public.reports;
    drop policy if exists backend_full_access_facilities on public.user_facilities;
    drop policy if exists backend_full_access_settings on public.zc_settings;
    drop policy if exists backend_full_access_audit on public.settings_audit;
    drop policy if exists audit_insert_system on public.settings_audit;
  end if;
end $$;

drop policy if exists ge_settings_audit_insert_own on public.settings_audit;
create policy ge_settings_audit_insert_own
on public.settings_audit
for insert
to authenticated
with check (user_id = auth.uid()::text);

drop policy if exists ge_settings_audit_read_own on public.settings_audit;
create policy ge_settings_audit_read_own
on public.settings_audit
for select
to authenticated
using (user_id = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- 3) Storage: keep fiscal PDFs/XML private and backend-only. Transport keeps
-- existing signed/backend folder policies by auth.uid() path.
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values
  ('fiscal-documents', 'fiscal-documents', false),
  ('transport-documents', 'transport-documents', false)
on conflict (id) do update set public = false;

drop policy if exists "ge_fiscal_docs_backend_only_select" on storage.objects;
create policy "ge_fiscal_docs_backend_only_select"
on storage.objects
for select
to authenticated
using (bucket_id = 'fiscal-documents' and false);

drop policy if exists "ge_fiscal_docs_backend_only_insert" on storage.objects;
create policy "ge_fiscal_docs_backend_only_insert"
on storage.objects
for insert
to authenticated
with check (bucket_id = 'fiscal-documents' and false);

drop policy if exists "ge_fiscal_docs_backend_only_update" on storage.objects;
create policy "ge_fiscal_docs_backend_only_update"
on storage.objects
for update
to authenticated
using (bucket_id = 'fiscal-documents' and false)
with check (bucket_id = 'fiscal-documents' and false);

drop policy if exists "ge_fiscal_docs_backend_only_delete" on storage.objects;
create policy "ge_fiscal_docs_backend_only_delete"
on storage.objects
for delete
to authenticated
using (bucket_id = 'fiscal-documents' and false);

-- ---------------------------------------------------------------------------
-- 4) Indexes for tenant/profile/status/date and missing FK hot paths.
-- ---------------------------------------------------------------------------

create index if not exists idx_user_sections_scope_status
  on public.user_sections (tenant_id, perfil_id, user_id, section, status);

create index if not exists idx_companies_scope_active
  on public.companies (tenant_id, active, id);

create index if not exists idx_subscriptions_scope_status
  on public.subscriptions (tenant_id, status, created_at desc);

create index if not exists idx_sat_credentials_scope_profile
  on public.sat_credentials (tenant_id, perfil_id, company_id, active, rfc);

create index if not exists idx_sat_sync_jobs_scope_profile_status
  on public.sat_sync_jobs (tenant_id, company_id, status, created_at desc);

create index if not exists idx_cfdi_sat_inbox_scope_profile_status
  on public.cfdi_sat_inbox (tenant_id, perfil_id, processed_status, fecha desc);

create index if not exists idx_detected_loads_scope_profile_status
  on public.detected_loads (tenant_id, perfil_id, status, created_at desc);

create index if not exists idx_detected_loads_cfdi_id
  on public.detected_loads (cfdi_id);

create index if not exists idx_fiscal_document_events_scope_module
  on public.fiscal_document_events (tenant_id, perfil_id, module, created_at desc);

create index if not exists idx_saas_billing_invoices_scope_status
  on public.saas_billing_invoices (tenant_id, status, created_at desc);

create index if not exists idx_tr_carta_aporte_tasks_scope_status
  on public.tr_carta_aporte_tasks (user_id, perfil_id, status, created_at desc);

create index if not exists idx_internal_user_sessions_internal_user_id
  on public.internal_user_sessions (internal_user_id);

create index if not exists idx_internal_users_chofer_id
  on public.internal_users (chofer_id);

create index if not exists idx_pac_responses_request_id
  on public.pac_responses (request_id);

create index if not exists idx_invoice_cancellations_request_ids
  on public.invoice_cancellations (pac_request_id, pac_response_id);

create index if not exists idx_tr_cfdi_perfil_id
  on public.tr_cfdi (perfil_id);

create index if not exists idx_tr_cfdi_user_perfil_created
  on public.tr_cfdi (user_id, perfil_id, created_at desc);

create index if not exists idx_tr_viajes_user_perfil_status
  on public.tr_viajes (user_id, perfil_id, status, created_at desc);

create index if not exists idx_tr_settings_user_perfil
  on public.tr_settings (user_id, perfil_id);

create index if not exists idx_tr_choferes_vehiculo_frecuente
  on public.tr_choferes (vehiculo_frecuente_id);

create index if not exists idx_tr_cliente_contactos_cliente_id
  on public.tr_cliente_contactos (cliente_id);

create index if not exists idx_tr_clientes_defaults
  on public.tr_clientes (destino_default_id, ruta_default_id, producto_default_id);

create index if not exists idx_tr_facturas_servicio_cliente_id
  on public.tr_facturas_servicio (cliente_id);

create index if not exists idx_tr_facturas_servicio_cartas_factura_id
  on public.tr_facturas_servicio_cartas (factura_servicio_id);

create index if not exists idx_tr_gastos_viaje_scope
  on public.tr_gastos_viaje (viaje_id, chofer_id, documento_id);

create index if not exists idx_tr_liquidacion_items_scope
  on public.tr_liquidacion_items (liquidacion_id, viaje_id);

create index if not exists idx_tr_liquidaciones_chofer_id
  on public.tr_liquidaciones (chofer_id);

create index if not exists idx_tr_notificaciones_viaje_id
  on public.tr_notificaciones (viaje_id);

create index if not exists idx_tr_operador_accesos_chofer_id
  on public.tr_operador_accesos (chofer_id);

-- ---------------------------------------------------------------------------
-- 5) Legacy scope report. No automatic mutation: this is evidence for a
-- controlled cleanup/mapping migration after product validation.
-- ---------------------------------------------------------------------------

create or replace view public.security_legacy_scope_report as
select
  'user_sections'::text as table_name,
  id::text as row_id,
  user_id::text as user_id,
  tenant_id::text as tenant_id,
  perfil_id::text as perfil_id,
  section::text as module_or_type,
  status::text as status,
  created_at as created_at,
  jsonb_build_object('role', role, 'display_name', display_name) as evidence
from public.user_sections
where status = 'active' and perfil_id is null
union all
select
  'tr_viajes',
  id::text,
  user_id::text,
  null,
  perfil_id::text,
  tipo_cfdi::text,
  status::text,
  created_at,
  jsonb_build_object('rfc_receptor', rfc_receptor, 'nombre_receptor', nombre_receptor)
from public.tr_viajes
where perfil_id is null
union all
select
  'tr_cfdi',
  id::text,
  user_id::text,
  null,
  perfil_id::text,
  tipo_cfdi::text,
  status::text,
  created_at,
  jsonb_build_object('uuid_sat', uuid_sat, 'id_ccp', id_ccp)
from public.tr_cfdi
where perfil_id is null
union all
select
  'tr_settings',
  id::text,
  user_id::text,
  null,
  perfil_id::text,
  'settings',
  null,
  updated_at,
  jsonb_build_object(
    'data_keys',
    coalesce(
      (
        select jsonb_agg(k order by k)
        from jsonb_object_keys(coalesce(public.tr_settings.data, '{}'::jsonb)) as k
      ),
      '[]'::jsonb
    )
  )
from public.tr_settings
where perfil_id is null;

revoke all on public.security_legacy_scope_report from anon, authenticated;
comment on view public.security_legacy_scope_report is
  'Backend-only report of legacy rows missing perfil_id. Do not expose to browser clients.';

commit;
