-- GE CONTROL - Hardening SaaS post-schema visualizer
-- Safe/idempotent migration. No elimina tablas ni datos.

-- 1) Si hay usuarios legacy sin tenant_id, crea un tenant con el mismo UUID
--    del usuario para que las FK de perfiles/companies/subscriptions no fallen.
insert into public.tenants (id, name, status)
select distinct us.user_id, '', 'active'
from public.user_sections us
where us.tenant_id is null
on conflict (id) do nothing;

update public.user_sections us
set tenant_id = us.user_id
where us.tenant_id is null;

-- 2) Backfill de perfiles_empresa.tenant_id desde user_sections.
update public.perfiles_empresa pe
set tenant_id = us.tenant_id
from public.user_sections us
where pe.tenant_id is null
  and pe.user_id = us.user_id
  and us.tenant_id is not null;

-- 3) Suscripción default para tenants que aún no la tengan.
insert into public.subscriptions (tenant_id, plan_name, max_companies, status)
select t.id, 'Básico', 1, 'active'
from public.tenants t
where not exists (
  select 1 from public.subscriptions s
  where s.tenant_id = t.id
)
on conflict do nothing;

-- 4) Espejo companies para perfiles existentes.
insert into public.companies (id, tenant_id, name, rfc, active, created_at, updated_at)
select pe.id, pe.tenant_id, pe.nombre, pe.rfc, pe.activo, pe.created_at, pe.updated_at
from public.perfiles_empresa pe
where pe.tenant_id is not null
on conflict (id) do update
set tenant_id = excluded.tenant_id,
    name = excluded.name,
    rfc = excluded.rfc,
    active = excluded.active,
    updated_at = now();

-- 5) Índices/FK de aislamiento y búsquedas frecuentes.
create unique index if not exists idx_companies_tenant_id_unique
  on public.companies(tenant_id, id);

create index if not exists idx_internal_users_perfil_section
  on public.internal_users(perfil_id, section, role, status);

create unique index if not exists idx_internal_users_tenant_section_code
  on public.internal_users(tenant_id, section, code)
  where tenant_id is not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'internal_users_tenant_id_fkey'
  ) then
    alter table public.internal_users
      add constraint internal_users_tenant_id_fkey
      foreign key (tenant_id) references public.tenants(id);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'internal_users_perfil_id_fkey'
  ) then
    alter table public.internal_users
      add constraint internal_users_perfil_id_fkey
      foreign key (perfil_id) references public.perfiles_empresa(id);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'internal_users_chofer_id_fkey'
  ) then
    alter table public.internal_users
      add constraint internal_users_chofer_id_fkey
      foreign key (chofer_id) references public.tr_choferes(id);
  end if;
end $$;

