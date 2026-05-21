-- Compatibility layer for current GE Control Gas LP profiles.
-- The product architecture keeps company_id uuid for future normalized companies,
-- while today's Gas LP module scopes runtime access with integer perfil_id.

alter table public.sat_credentials add column if not exists perfil_id integer;
alter table public.sat_sync_jobs add column if not exists perfil_id integer;
alter table public.cfdi_sat_inbox add column if not exists perfil_id integer;
alter table public.detected_loads add column if not exists perfil_id integer;

create index if not exists idx_sat_credentials_perfil on public.sat_credentials (tenant_id, perfil_id, active);
create index if not exists idx_sat_sync_jobs_perfil on public.sat_sync_jobs (tenant_id, perfil_id, status, created_at desc);
create index if not exists idx_cfdi_sat_inbox_perfil on public.cfdi_sat_inbox (tenant_id, perfil_id, fecha desc);
create index if not exists idx_detected_loads_perfil on public.detected_loads (tenant_id, perfil_id, status, created_at desc);

comment on column public.sat_credentials.perfil_id is 'Current GE Control Gas LP company/profile scope. Keep company_id for future normalized company UUID.';
comment on column public.sat_sync_jobs.perfil_id is 'Current GE Control Gas LP company/profile scope.';
comment on column public.cfdi_sat_inbox.perfil_id is 'Current GE Control Gas LP company/profile scope.';
comment on column public.detected_loads.perfil_id is 'Current GE Control Gas LP company/profile scope.';
