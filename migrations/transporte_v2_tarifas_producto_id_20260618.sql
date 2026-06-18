alter table public.tr_tarifas
  add column if not exists producto_id bigint references public.tr_productos_operacion(id) on delete set null;

update public.tr_tarifas
set producto_id = nullif(metadata ->> 'producto_id', '')::bigint
where producto_id is null
  and metadata ? 'producto_id'
  and (metadata ->> 'producto_id') ~ '^[0-9]+$';

create index if not exists idx_tr_tarifas_ruta_producto_cliente
  on public.tr_tarifas(user_id, perfil_id, ruta_id, producto_id, cliente_id, activo);
