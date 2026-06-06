create table if not exists public.gas_lp_facility_carta_porte_config (
  id bigserial primary key,
  user_id text not null,
  tenant_id text,
  perfil_id bigint,
  facility_id bigint not null references public.user_facilities(id) on delete cascade,
  id_ubicacion_carta_porte text not null default '',
  tipo_ubicacion text not null default 'ambos',
  estado_sat text not null default '',
  municipio_sat text not null default '',
  localidad_sat text not null default '',
  referencia_carta_porte text not null default '',
  activo boolean not null default true,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, tenant_id, perfil_id, facility_id)
);

create index if not exists idx_gas_lp_facility_cp_config_scope
  on public.gas_lp_facility_carta_porte_config(user_id, tenant_id, perfil_id, activo);

create index if not exists idx_gas_lp_facility_cp_config_facility
  on public.gas_lp_facility_carta_porte_config(facility_id);
