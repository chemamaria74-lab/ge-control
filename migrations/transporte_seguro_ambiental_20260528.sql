-- GE Control - Transporte: seguro ambiental para Carta Porte con material peligroso

begin;

alter table public.tr_vehiculos
  add column if not exists aseguradora_medio_ambiente text not null default '',
  add column if not exists poliza_medio_ambiente text not null default '';

commit;
