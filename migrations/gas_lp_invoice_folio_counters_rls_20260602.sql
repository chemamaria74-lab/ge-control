-- GE Control - Hardening RLS para contador de folios Gas LP.
-- La tabla es backend-only: el service_role conserva acceso y los clientes
-- anon/authenticated no pueden leer, insertar, actualizar ni borrar directo.

begin;

alter table if exists public.gas_lp_invoice_folio_counters enable row level security;

revoke all on table public.gas_lp_invoice_folio_counters from anon, authenticated;
grant all on table public.gas_lp_invoice_folio_counters to service_role;

do $$
begin
  if to_regclass('public.gas_lp_invoice_folio_counters_id_seq') is not null then
    revoke all on sequence public.gas_lp_invoice_folio_counters_id_seq from anon, authenticated;
    grant all on sequence public.gas_lp_invoice_folio_counters_id_seq to service_role;
  end if;
end;
$$;

drop policy if exists ge_gas_lp_invoice_folio_counters_backend_only on public.gas_lp_invoice_folio_counters;
create policy ge_gas_lp_invoice_folio_counters_backend_only
on public.gas_lp_invoice_folio_counters
for all
to anon, authenticated
using (false)
with check (false);

do $$
begin
  if to_regprocedure('public.next_gas_lp_invoice_folio(uuid, uuid, bigint, text)') is not null then
    revoke all on function public.next_gas_lp_invoice_folio(uuid, uuid, bigint, text) from public, anon, authenticated;
    grant execute on function public.next_gas_lp_invoice_folio(uuid, uuid, bigint, text) to service_role;
  end if;
end;
$$;

commit;
