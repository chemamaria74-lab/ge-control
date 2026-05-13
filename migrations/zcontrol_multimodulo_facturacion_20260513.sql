-- ZControl: multi-modulo y factura de servicio transporte
-- Ejecutar en Supabase SQL editor.

alter table if exists tr_viajes
  add column if not exists regimen_fiscal_receptor text default '601';

alter table if exists tr_facturas_servicio
  add column if not exists uuid_sat text default '',
  add column if not exists xml_content text default '',
  add column if not exists pdf_url text default '';

create table if not exists tr_facturas_servicio_cartas (
  id bigserial primary key,
  user_id uuid not null,
  factura_servicio_id bigint references tr_facturas_servicio(id) on delete cascade,
  viaje_id bigint not null,
  created_at timestamptz default now(),
  unique (user_id, viaje_id)
);

create index if not exists idx_tr_fact_serv_cartas_user
  on tr_facturas_servicio_cartas(user_id);

create index if not exists idx_tr_viajes_user_status
  on tr_viajes(user_id, status);

-- Asegura que un mismo usuario pueda tener Transporte y Gas LP a la vez.
-- La app ahora lee todas las filas de user_sections, no solo la primera.
create unique index if not exists idx_user_sections_user_section
  on user_sections(user_id, section);
