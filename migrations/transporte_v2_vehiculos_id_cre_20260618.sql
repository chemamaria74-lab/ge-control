-- Transporte v2 - ID CRE pertenece al vehiculo, no al operador.

alter table if exists public.tr_vehiculos
  add column if not exists id_cre text;

comment on column public.tr_vehiculos.id_cre is
  'Identificador CRE de la unidad/vehiculo de transporte; se captura en catalogo Vehiculos.';
