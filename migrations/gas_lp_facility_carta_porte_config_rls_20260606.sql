-- GE Control - RLS para configuracion Carta Porte por instalacion Gas LP.
-- Idempotente: corrige tabla creada sin RLS/policies.

begin;

alter table if exists public.gas_lp_facility_carta_porte_config
  enable row level security;

drop policy if exists ge_gas_lp_facility_cp_config_own_rows
  on public.gas_lp_facility_carta_porte_config;

create policy ge_gas_lp_facility_cp_config_own_rows
on public.gas_lp_facility_carta_porte_config
for all to authenticated
using (
  user_id = auth.uid()::text
  and perfil_id is not null
  and exists (
    select 1 from public.user_sections us
    where us.user_id = auth.uid()
      and us.status = 'active'
      and us.section = 'gas_lp'
      and us.perfil_id = gas_lp_facility_carta_porte_config.perfil_id
  )
)
with check (user_id = auth.uid()::text and perfil_id is not null);

commit;
