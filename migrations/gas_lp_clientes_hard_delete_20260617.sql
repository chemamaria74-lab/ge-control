delete from public.gas_lp_clientes_facturacion
where activo is not true;

alter table if exists public.gas_lp_clientes_facturacion
  drop constraint if exists gas_lp_clientes_facturacion_activo_true;

alter table if exists public.gas_lp_clientes_facturacion
  add constraint gas_lp_clientes_facturacion_activo_true check (activo is true);
