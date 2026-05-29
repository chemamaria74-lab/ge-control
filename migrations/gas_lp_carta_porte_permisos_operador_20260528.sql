-- GE Control - Gas LP Carta Porte: permisos SCT y operador vigente
-- La Carta Porte de traspaso no debe salir con permisos ficticios ni chofer sin vigencias.

begin;

alter table public.gas_lp_vehiculos
  add column if not exists permiso_sct text not null default 'TPAF01',
  add column if not exists num_permiso_sct text not null default '';

alter table public.gas_lp_choferes
  add column if not exists tipo_licencia text not null default '',
  add column if not exists licencia_vigencia date,
  add column if not exists examen_medico_vigencia date;

comment on column public.gas_lp_vehiculos.permiso_sct is
  'Clave SAT/SICT PermSCT para Carta Porte. Default operativo: TPAF01; validar contra permiso real del cliente.';
comment on column public.gas_lp_vehiculos.num_permiso_sct is
  'Numero de permiso SCT/SICT del autotransportista. Obligatorio para timbrar Carta Porte Gas LP.';
comment on column public.gas_lp_choferes.tipo_licencia is
  'Categoria de licencia federal del conductor. Para materiales peligrosos Gas LP GE Control exige E.';
comment on column public.gas_lp_choferes.licencia_vigencia is
  'Fecha de vigencia de licencia del operador.';
comment on column public.gas_lp_choferes.examen_medico_vigencia is
  'Fecha de vigencia/validez de examen o aptitud psicofisica del operador.';

commit;
