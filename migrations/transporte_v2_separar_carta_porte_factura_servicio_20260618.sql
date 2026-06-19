-- Separa estados y artefactos fiscales de Carta Porte Traslado vs Factura de servicio/flete.
-- Aditiva e idempotente: no borra datos ni cambia tarifas.

alter table if exists public.tr_viajes
  add column if not exists carta_porte_uuid text,
  add column if not exists carta_porte_pdf_url text,
  add column if not exists carta_porte_xml_url text,
  add column if not exists factura_servicio_status text default 'pendiente',
  add column if not exists factura_servicio_uuid text,
  add column if not exists factura_servicio_pdf_url text,
  add column if not exists factura_servicio_xml_url text,
  add column if not exists factura_carga_pdf_url text;

alter table if exists public.tr_cfdi
  add column if not exists documento_fiscal_tipo text default 'carta_porte_traslado',
  add column if not exists idempotency_key text;

alter table if exists public.tr_facturas_servicio
  add column if not exists email_receptor text,
  add column if not exists pdf_url text,
  add column if not exists idempotency_key text,
  add column if not exists metadata jsonb default '{}'::jsonb;

create unique index if not exists idx_tr_cfdi_idempotency
  on public.tr_cfdi(user_id, perfil_id, idempotency_key)
  where idempotency_key is not null and idempotency_key <> '';

create unique index if not exists idx_tr_facturas_servicio_idempotency
  on public.tr_facturas_servicio(user_id, perfil_id, idempotency_key)
  where idempotency_key is not null and idempotency_key <> '';

create index if not exists idx_tr_cfdi_carta_porte_traslado
  on public.tr_cfdi(user_id, perfil_id, tipo_cfdi, status, fecha_timbrado desc);

comment on column public.tr_viajes.carta_porte_uuid is
  'UUID SAT del CFDI Traslado con Complemento Carta Porte 3.1.';
comment on column public.tr_viajes.factura_servicio_uuid is
  'UUID SAT de la factura de servicio/flete, CFDI Ingreso independiente.';
comment on column public.tr_viajes.factura_carga_pdf_url is
  'PDF de la factura de carga subida por operador/admin.';
