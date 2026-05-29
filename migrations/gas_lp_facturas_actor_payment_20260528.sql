alter table if exists public.gas_lp_facturas
  add column if not exists created_by_internal bigint,
  add column if not exists created_by_internal_name text not null default '',
  add column if not exists payment_status text not null default 'no_aplica';

create index if not exists idx_gas_lp_facturas_actor
  on public.gas_lp_facturas (perfil_id, created_by_internal, created_at desc);

create index if not exists idx_gas_lp_facturas_payment_status
  on public.gas_lp_facturas (perfil_id, payment_status, created_at desc);

update public.gas_lp_facturas
set
  created_by_internal = nullif(metadata->>'internal_user_id', '')::bigint,
  created_by_internal_name = coalesce(metadata->>'created_by_internal_name', metadata->>'created_by', created_by_internal_name)
where created_by_internal is null
  and jsonb_typeof(metadata) = 'object'
  and (metadata->>'internal_user_id') ~ '^[0-9]+$';

update public.gas_lp_facturas f
set created_by_internal_name = coalesce(nullif(u.display_name, ''), nullif(u.code, ''), f.created_by_internal_name)
from public.internal_users u
where f.created_by_internal = u.id
  and coalesce(f.created_by_internal_name, '') = '';

update public.gas_lp_facturas
set payment_status = case
  when upper(coalesce(metadata->>'metodo_pago', '')) = 'PPD' then 'pendiente_complemento'
  when coalesce(metadata->>'tipo_operacion', '') = 'traspaso' then 'no_aplica'
  else 'pagado_pue'
end
where payment_status = 'no_aplica'
  and jsonb_typeof(metadata) = 'object'
  and coalesce(metadata->>'tipo_operacion', '') <> '';
