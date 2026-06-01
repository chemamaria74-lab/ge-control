-- GE Control - Folios consecutivos Gas LP por empresa/perfil/serie

begin;

create table if not exists public.gas_lp_invoice_folio_counters (
  id bigserial primary key,
  user_id uuid not null,
  tenant_key text not null default '',
  perfil_key text not null default '',
  serie text not null,
  last_folio bigint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, tenant_key, perfil_key, serie)
);

create or replace function public.next_gas_lp_invoice_folio(
  p_user_id uuid,
  p_tenant_id uuid,
  p_perfil_id bigint,
  p_serie text
) returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  v_next bigint;
begin
  if p_user_id is null then
    raise exception 'p_user_id is required';
  end if;

  insert into public.gas_lp_invoice_folio_counters (
    user_id,
    tenant_key,
    perfil_key,
    serie,
    last_folio
  )
  values (
    p_user_id,
    coalesce(p_tenant_id::text, ''),
    coalesce(p_perfil_id::text, ''),
    upper(left(regexp_replace(coalesce(p_serie, 'AA'), '[^A-Za-z0-9]', '', 'g'), 10)),
    1
  )
  on conflict (user_id, tenant_key, perfil_key, serie)
  do update set
    last_folio = public.gas_lp_invoice_folio_counters.last_folio + 1,
    updated_at = now()
  returning last_folio into v_next;

  return v_next;
end;
$$;

commit;
