-- Transporte v2 - Cartas Porte emitidas sin errores en Hoy/Todas.
-- Aditiva e idempotente: no borra datos ni cambia XML timbrados.

alter table if exists public.tr_cfdi
  add column if not exists perfil_id bigint,
  add column if not exists viaje_id bigint,
  add column if not exists tipo_cfdi text default 'T',
  add column if not exists uuid_sat text,
  add column if not exists id_ccp text,
  add column if not exists xml_content text,
  add column if not exists pdf_url text,
  add column if not exists status text default 'Vigente',
  add column if not exists fecha_timbrado timestamptz,
  add column if not exists rfc_receptor text,
  add column if not exists volumen_total numeric default 0,
  add column if not exists importe_total numeric default 0,
  add column if not exists num_permiso_cne text,
  add column if not exists documento_fiscal_tipo text default 'carta_porte_traslado',
  add column if not exists idempotency_key text,
  add column if not exists metadata jsonb default '{}'::jsonb,
  add column if not exists created_at timestamptz default now();

alter table if exists public.tr_viajes
  add column if not exists carta_porte_uuid text,
  add column if not exists carta_porte_pdf_url text,
  add column if not exists carta_porte_xml_url text,
  add column if not exists carta_porte_status text default 'pendiente';

create index if not exists idx_tr_cfdi_cp_emitidas
  on public.tr_cfdi(user_id, perfil_id, tipo_cfdi, status, fecha_timbrado desc)
  where tipo_cfdi = 'T';

create index if not exists idx_tr_cfdi_cp_viaje
  on public.tr_cfdi(user_id, perfil_id, viaje_id, fecha_timbrado desc)
  where tipo_cfdi = 'T';

create unique index if not exists idx_tr_cfdi_cp_idempotency
  on public.tr_cfdi(user_id, perfil_id, idempotency_key)
  where idempotency_key is not null and idempotency_key <> '';

comment on column public.tr_cfdi.xml_content is
  'XML timbrado completo. Transporte v2 lee Hoy/Todas desde este XML para no inventar datos.';
comment on column public.tr_cfdi.pdf_url is
  'URL PAC si SW devuelve PDF. Transporte v2 también puede generar PDF propio desde xml_content.';
comment on column public.tr_cfdi.documento_fiscal_tipo is
  'carta_porte_traslado para CFDI T + Complemento Carta Porte; factura_servicio para CFDI I separado.';
