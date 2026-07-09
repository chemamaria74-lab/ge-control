-- Transporte v2: Carta Ingreso como flujo visible de facturación de flete.
-- Mantiene compatibilidad con registros legacy de factura de servicio simple.

alter table if exists public.tr_facturas_servicio
  add column if not exists tipo text not null default 'factura_servicio',
  add column if not exists uuid_carta_ingreso text,
  add column if not exists uuid_carta_porte_base text,
  add column if not exists status_timbrado text,
  add column if not exists xml_path text,
  add column if not exists pdf_path text;

update public.tr_facturas_servicio
set tipo = 'carta_ingreso',
    uuid_carta_ingreso = coalesce(uuid_carta_ingreso, uuid_sat),
    uuid_carta_porte_base = coalesce(uuid_carta_porte_base, metadata->>'uuid_carta_porte_base'),
    status_timbrado = coalesce(status_timbrado, status)
where metadata->>'tipo' = 'carta_ingreso';

create index if not exists idx_tr_facturas_servicio_tipo
  on public.tr_facturas_servicio (user_id, perfil_id, tipo);

create index if not exists idx_tr_facturas_servicio_uuid_ci
  on public.tr_facturas_servicio (uuid_carta_ingreso)
  where uuid_carta_ingreso is not null;

comment on column public.tr_facturas_servicio.tipo is
  'factura_servicio=legacy simple; carta_ingreso=CFDI I con Complemento Carta Porte 3.1';

comment on column public.tr_facturas_servicio.uuid_carta_porte_base is
  'UUID de la Carta Porte Traslado usada como base operativa para Carta Ingreso.';
