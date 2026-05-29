-- GE Control - Gas LP Carta Porte: seguro ambiental para material peligroso

begin;

alter table public.gas_lp_vehiculos
  add column if not exists aseguradora_medio_ambiente text not null default '',
  add column if not exists poliza_medio_ambiente text not null default '';

comment on column public.gas_lp_vehiculos.aseguradora_medio_ambiente is
  'Aseguradora de medio ambiente para Carta Porte con material peligroso.';
comment on column public.gas_lp_vehiculos.poliza_medio_ambiente is
  'Poliza de medio ambiente para Carta Porte con material peligroso.';

commit;
