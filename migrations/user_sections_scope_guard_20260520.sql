-- GE CONTROL - Guard rails para evitar nuevos accesos activos sin tenant.
-- Safe/idempotent: primero repara legado con tenant=user_id, luego agrega constraint parcial.

insert into public.tenants (id, name, status)
select distinct us.user_id, coalesce(au.email, ''), 'active'
from public.user_sections us
left join auth.users au on au.id = us.user_id
where us.tenant_id is null
on conflict (id) do nothing;

update public.user_sections
set tenant_id = user_id
where tenant_id is null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'user_sections_active_requires_tenant'
  ) then
    alter table public.user_sections
      add constraint user_sections_active_requires_tenant
      check (coalesce(status, 'active') <> 'active' or tenant_id is not null)
      not valid;
  end if;
end $$;

create index if not exists idx_user_sections_missing_tenant_report
  on public.user_sections(user_id, section, status)
  where tenant_id is null;
