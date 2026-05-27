-- GE Control - Providers multiempresa unique scope
-- Permite registrar el mismo RFC proveedor en distintas empresas/perfiles del
-- mismo usuario. La unicidad fiscal operativa queda en user_id + perfil_id + RFC.

begin;

alter table if exists public.providers
  add column if not exists perfil_id bigint;

do $$
declare
  c record;
  col_names text[];
begin
  for c in
    select conname, conrelid
    from pg_constraint
    where conrelid = 'public.providers'::regclass
      and contype = 'u'
  loop
    select array_agg(a.attname order by ord.n)
      into col_names
    from unnest(c.conkey) with ordinality as ord(attnum, n)
    join pg_attribute a
      on a.attrelid = c.conrelid
     and a.attnum = ord.attnum;

    if col_names = array['user_id', 'rfc'] then
      execute format('alter table public.providers drop constraint %I', c.conname);
    end if;
  end loop;
end $$;

do $$
declare
  i record;
begin
  for i in
    select indexname
    from pg_indexes
    where schemaname = 'public'
      and tablename = 'providers'
      and indexdef ilike '%unique%'
      and indexdef ilike '%user_id%'
      and indexdef ilike '%rfc%'
      and indexdef not ilike '%perfil_id%'
  loop
    execute format('drop index if exists public.%I', i.indexname);
  end loop;
end $$;

create unique index if not exists providers_user_perfil_rfc_unique
  on public.providers(user_id, perfil_id, upper(rfc))
  where perfil_id is not null;

create index if not exists idx_providers_user_perfil
  on public.providers(user_id, perfil_id);

commit;
