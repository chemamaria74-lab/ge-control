-- Gas LP invoices: promote operational fields out of metadata for reliable assistant queries.
-- Keep metadata for backwards compatibility, but make issuer/date/payment/discount fields queryable.

alter table if exists public.gas_lp_facturas
  add column if not exists rfc_emisor text,
  add column if not exists empresa_rfc text,
  add column if not exists empresa_nombre text,
  add column if not exists fecha_emision timestamptz,
  add column if not exists metodo_pago text,
  add column if not exists forma_pago text,
  add column if not exists saldo_insoluto numeric(14,2),
  add column if not exists total numeric(14,2),
  add column if not exists subtotal numeric(14,2),
  add column if not exists iva numeric(14,2),
  add column if not exists descuento_total numeric(14,2),
  add column if not exists tipo_operacion text,
  add column if not exists is_transfer boolean,
  add column if not exists cliente_id bigint,
  add column if not exists cliente_nombre text,
  add column if not exists receptor_nombre text,
  add column if not exists origen_nombre text,
  add column if not exists destino_nombre text,
  add column if not exists serie text,
  add column if not exists folio_usuario text,
  add column if not exists tipo_descuento text,
  add column if not exists descuento_confirmado numeric(14,2),
  add column if not exists descuento_por_litro numeric(14,6),
  add column if not exists precio_unitario numeric(14,6),
  add column if not exists precio_unitario_original numeric(14,6),
  add column if not exists litros_confirmados numeric(14,4),
  add column if not exists clave_prod_serv text,
  add column if not exists unidad text,
  add column if not exists no_identificacion text,
  add column if not exists created_from text,
  add column if not exists generar_carta_porte boolean;

create or replace function public._gas_lp_migration_numeric(value text)
returns numeric
language sql
immutable
as $$
  select case
    when nullif(btrim(value), '') ~ '^-?[0-9]+(\.[0-9]+)?$' then nullif(btrim(value), '')::numeric
    else null
  end
$$;

with parsed as (
  select
    f.id,
    nullif(f.metadata->>'rfc_emisor', '') as md_rfc_emisor,
    nullif(f.metadata->>'empresa_rfc', '') as md_empresa_rfc,
    nullif(f.metadata->>'empresa_asignada_rfc', '') as md_empresa_asignada_rfc,
    nullif(f.metadata->>'empresa_asignada_nombre', '') as md_empresa_asignada_nombre,
    nullif(f.metadata->>'empresa_nombre', '') as md_empresa_nombre,
    nullif(f.metadata->>'metodo_pago', '') as md_metodo_pago,
    nullif(f.metadata->>'forma_pago', '') as md_forma_pago,
    nullif(f.metadata->>'tipo_operacion', '') as md_tipo_operacion,
    nullif(f.metadata->>'operation_type', '') as md_operation_type,
    nullif(f.metadata->>'cliente_nombre', '') as md_cliente_nombre,
    nullif(f.metadata->>'receptor_nombre', '') as md_receptor_nombre,
    nullif(f.metadata->>'origen_nombre', '') as md_origen_nombre,
    nullif(f.metadata->>'destino_nombre', '') as md_destino_nombre,
    nullif(f.metadata->>'serie', '') as md_serie,
    nullif(f.metadata->>'folio_usuario', '') as md_folio_usuario,
    nullif(f.metadata->>'tipo_descuento_confirmado', '') as md_tipo_descuento_confirmado,
    nullif(f.metadata->>'tipo_descuento', '') as md_tipo_descuento,
    nullif(f.metadata->>'clave_prod_serv', '') as md_clave_prod_serv,
    nullif(f.metadata->>'unidad', '') as md_unidad,
    nullif(f.metadata->>'no_identificacion', '') as md_no_identificacion,
    nullif(f.metadata->>'created_from', '') as md_created_from,
    nullif(f.metadata->>'payment_status', '') as md_payment_status,
    nullif(substring(f.xml_content from '<[^>]*Emisor[^>]* Rfc="([^"]+)"'), '') as xml_rfc_emisor,
    nullif(substring(f.xml_content from '<[^>]*Comprobante[^>]* Fecha="([^"]+)"'), '') as xml_fecha,
    nullif(substring(f.xml_content from '<[^>]*Comprobante[^>]* MetodoPago="([^"]+)"'), '') as xml_metodo_pago,
    nullif(substring(f.xml_content from '<[^>]*Comprobante[^>]* FormaPago="([^"]+)"'), '') as xml_forma_pago,
    public._gas_lp_migration_numeric(substring(f.xml_content from '<[^>]*Comprobante[^>]* SubTotal="([^"]+)"')) as xml_subtotal,
    public._gas_lp_migration_numeric(substring(f.xml_content from '<[^>]*Comprobante[^>]* Descuento="([^"]+)"')) as xml_descuento,
    public._gas_lp_migration_numeric(substring(f.xml_content from '<[^>]*Comprobante[^>]* Total="([^"]+)"')) as xml_total,
    public._gas_lp_migration_numeric(f.metadata->>'total') as md_total,
    public._gas_lp_migration_numeric(f.metadata->>'total_confirmado') as md_total_confirmado,
    public._gas_lp_migration_numeric(f.metadata->>'total_preview') as md_total_preview,
    public._gas_lp_migration_numeric(f.metadata->>'subtotal') as md_subtotal,
    public._gas_lp_migration_numeric(f.metadata->>'subtotal_confirmado') as md_subtotal_confirmado,
    public._gas_lp_migration_numeric(f.metadata->>'iva') as md_iva,
    public._gas_lp_migration_numeric(f.metadata->>'iva_confirmado') as md_iva_confirmado,
    public._gas_lp_migration_numeric(f.metadata->>'descuento') as md_descuento,
    public._gas_lp_migration_numeric(f.metadata->>'descuento_confirmado') as md_descuento_confirmado,
    public._gas_lp_migration_numeric(f.metadata->>'descuento_preview') as md_descuento_preview,
    public._gas_lp_migration_numeric(f.metadata->>'descuento_total') as md_descuento_total,
    public._gas_lp_migration_numeric(f.metadata->>'descuento_por_litro') as md_descuento_por_litro,
    public._gas_lp_migration_numeric(f.metadata->>'precio_unitario') as md_precio_unitario,
    public._gas_lp_migration_numeric(f.metadata->>'precio_unitario_original') as md_precio_unitario_original,
    public._gas_lp_migration_numeric(f.metadata->>'litros_confirmados') as md_litros_confirmados,
    public._gas_lp_migration_numeric(f.metadata->>'saldo_insoluto') as md_saldo_insoluto,
    public._gas_lp_migration_numeric(f.metadata->>'cliente_id') as md_cliente_id,
    case
      when lower(coalesce(f.metadata->>'is_transfer', '')) in ('true', 't', '1', 'yes', 'si') then true
      when lower(coalesce(f.metadata->>'is_transfer', '')) in ('false', 'f', '0', 'no') then false
      else null
    end as md_is_transfer,
    case
      when lower(coalesce(f.metadata->>'generar_carta_porte', '')) in ('true', 't', '1', 'yes', 'si') then true
      when lower(coalesce(f.metadata->>'generar_carta_porte', '')) in ('false', 'f', '0', 'no') then false
      else null
    end as md_generar_carta_porte
  from public.gas_lp_facturas f
),
resolved as (
  select
    p.*,
    coalesce(nullif(f.rfc_emisor, ''), p.md_rfc_emisor, p.md_empresa_rfc, p.md_empresa_asignada_rfc, p.xml_rfc_emisor) as rfc_emisor_value,
    coalesce(nullif(f.empresa_rfc, ''), p.md_empresa_rfc, p.md_rfc_emisor, p.md_empresa_asignada_rfc, p.xml_rfc_emisor) as empresa_rfc_value,
    coalesce(nullif(f.empresa_nombre, ''), p.md_empresa_nombre, p.md_empresa_asignada_nombre) as empresa_nombre_value,
    coalesce(nullif(f.metodo_pago, ''), p.md_metodo_pago, p.xml_metodo_pago) as metodo_pago_value,
    coalesce(nullif(f.forma_pago, ''), p.md_forma_pago, p.xml_forma_pago) as forma_pago_value,
    coalesce(f.total, p.md_total, p.md_total_confirmado, p.md_total_preview, p.xml_total, round(coalesce(f.importe, 0)::numeric * 1.16, 2)) as total_value,
    coalesce(f.subtotal, p.md_subtotal, p.md_subtotal_confirmado, p.xml_subtotal, f.importe) as subtotal_value,
    coalesce(f.iva, p.md_iva, p.md_iva_confirmado) as iva_value,
    coalesce(f.descuento_total, p.md_descuento_confirmado, p.md_descuento_preview, p.md_descuento_total, p.md_descuento, p.xml_descuento) as descuento_value
  from public.gas_lp_facturas f
  join parsed p on p.id = f.id
)
update public.gas_lp_facturas f
set
  rfc_emisor = r.rfc_emisor_value,
  empresa_rfc = r.empresa_rfc_value,
  empresa_nombre = r.empresa_nombre_value,
  fecha_emision = coalesce(
    f.fecha_emision,
    case when coalesce(f.metadata->>'fecha_emision', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' then (f.metadata->>'fecha_emision')::timestamptz else null end,
    case when coalesce(f.metadata->>'fecha_cfdi', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' then (f.metadata->>'fecha_cfdi')::timestamptz else null end,
    case when coalesce(r.xml_fecha, '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' then r.xml_fecha::timestamptz else null end,
    f.fecha_timbrado,
    f.created_at
  ),
  metodo_pago = r.metodo_pago_value,
  forma_pago = r.forma_pago_value,
  total = r.total_value,
  subtotal = r.subtotal_value,
  iva = coalesce(r.iva_value, r.total_value - r.subtotal_value),
  descuento_total = coalesce(r.descuento_value, 0),
  saldo_insoluto = coalesce(
    f.saldo_insoluto,
    r.md_saldo_insoluto,
    case when upper(coalesce(r.metodo_pago_value, '')) = 'PPD' then r.total_value else 0 end
  ),
  payment_status = case
    when coalesce(nullif(f.payment_status, ''), '') in ('', 'no_aplica') then coalesce(
      r.md_payment_status,
      case when upper(coalesce(r.metodo_pago_value, '')) = 'PPD' then 'pendiente_complemento' else 'pagado_pue' end
    )
    else f.payment_status
  end,
  tipo_operacion = coalesce(nullif(f.tipo_operacion, ''), r.md_tipo_operacion, r.md_operation_type),
  is_transfer = coalesce(f.is_transfer, r.md_is_transfer, r.md_tipo_operacion = 'traspaso', r.md_operation_type = 'transfer'),
  cliente_id = coalesce(f.cliente_id, r.md_cliente_id::bigint),
  cliente_nombre = coalesce(nullif(f.cliente_nombre, ''), r.md_cliente_nombre, r.md_receptor_nombre),
  receptor_nombre = coalesce(nullif(f.receptor_nombre, ''), r.md_receptor_nombre, r.md_cliente_nombre),
  origen_nombre = coalesce(nullif(f.origen_nombre, ''), r.md_origen_nombre),
  destino_nombre = coalesce(nullif(f.destino_nombre, ''), r.md_destino_nombre),
  serie = coalesce(nullif(f.serie, ''), r.md_serie),
  folio_usuario = coalesce(nullif(f.folio_usuario, ''), r.md_folio_usuario),
  tipo_descuento = coalesce(nullif(f.tipo_descuento, ''), r.md_tipo_descuento_confirmado, r.md_tipo_descuento),
  descuento_confirmado = coalesce(f.descuento_confirmado, r.md_descuento_confirmado, r.md_descuento_preview),
  descuento_por_litro = coalesce(f.descuento_por_litro, r.md_descuento_por_litro),
  precio_unitario = coalesce(f.precio_unitario, r.md_precio_unitario),
  precio_unitario_original = coalesce(f.precio_unitario_original, r.md_precio_unitario_original),
  litros_confirmados = coalesce(f.litros_confirmados, r.md_litros_confirmados, f.volumen_litros),
  clave_prod_serv = coalesce(nullif(f.clave_prod_serv, ''), r.md_clave_prod_serv),
  unidad = coalesce(nullif(f.unidad, ''), r.md_unidad),
  no_identificacion = coalesce(nullif(f.no_identificacion, ''), r.md_no_identificacion),
  created_from = coalesce(nullif(f.created_from, ''), r.md_created_from),
  generar_carta_porte = coalesce(f.generar_carta_porte, r.md_generar_carta_porte),
  updated_at = coalesce(f.updated_at, now())
from resolved r
where f.id = r.id;

with latest as (
  select distinct on (factura_id)
    factura_id,
    saldo_insoluto,
    complemento_id
  from public.gas_lp_complementos_pago_facturas
  where status = 'timbrado'
  order by factura_id, created_at desc nulls last, id desc
)
update public.gas_lp_facturas f
set
  saldo_insoluto = latest.saldo_insoluto,
  payment_status = case
    when coalesce(latest.saldo_insoluto, 0) <= 0 then 'pagado_con_complemento'
    else 'pago_parcial'
  end,
  metadata = coalesce(f.metadata, '{}'::jsonb) || jsonb_build_object(
    'saldo_insoluto', latest.saldo_insoluto,
    'payment_status', case when coalesce(latest.saldo_insoluto, 0) <= 0 then 'pagado_con_complemento' else 'pago_parcial' end,
    'ultimo_complemento_pago_id', latest.complemento_id
  ),
  updated_at = now()
from latest
where f.id = latest.factura_id;

create index if not exists idx_gas_lp_facturas_empresa_fecha_emision
  on public.gas_lp_facturas (empresa_rfc, fecha_emision desc);

create index if not exists idx_gas_lp_facturas_emisor_fecha_emision
  on public.gas_lp_facturas (rfc_emisor, fecha_emision desc);

create index if not exists idx_gas_lp_facturas_empresa_receptor_fecha
  on public.gas_lp_facturas (empresa_rfc, rfc_receptor, fecha_emision desc);

create index if not exists idx_gas_lp_facturas_empresa_pago_saldo
  on public.gas_lp_facturas (empresa_rfc, metodo_pago, saldo_insoluto);

create index if not exists idx_gas_lp_facturas_empresa_descuento
  on public.gas_lp_facturas (empresa_rfc, fecha_emision desc)
  where coalesce(descuento_total, 0) > 0
     or coalesce(descuento_confirmado, 0) > 0
     or coalesce(descuento_por_litro, 0) > 0;

drop function if exists public._gas_lp_migration_numeric(text);
