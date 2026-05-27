-- GE Control - Gas LP Carta Porte catalogs
-- Idempotente: crea tablas si faltan y agrega columnas si la tabla ya existia incompleta.

begin;

create table if not exists public.gas_lp_choferes (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  nombre text not null default '',
  rfc text not null default '',
  licencia text not null default '',
  telefono text not null default '',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gas_lp_vehiculos (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  facility_id bigint,
  placas text not null default '',
  modelo text not null default '',
  anio integer not null default 2020,
  permiso_cre text not null default '',
  poliza_seguro text not null default '',
  aseguradora text not null default '',
  config_vehicular text not null default 'C2',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gas_lp_rutas (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  nombre text not null default '',
  origen_facility_id bigint,
  destino_facility_id bigint,
  cp_origen text not null default '',
  cp_destino text not null default '',
  distancia_km numeric not null default 1,
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.gas_lp_choferes
  add column if not exists tenant_id uuid,
  add column if not exists perfil_id bigint,
  add column if not exists legacy_sqlite_id bigint,
  add column if not exists source text not null default 'supabase',
  add column if not exists modulo_propietario text not null default 'gas_lp',
  add column if not exists rfc text not null default '',
  add column if not exists licencia text not null default '',
  add column if not exists telefono text not null default '',
  add column if not exists activo boolean not null default true,
  add column if not exists metadata jsonb not null default '{}'::jsonb,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

alter table public.gas_lp_vehiculos
  add column if not exists tenant_id uuid,
  add column if not exists perfil_id bigint,
  add column if not exists legacy_sqlite_id bigint,
  add column if not exists source text not null default 'supabase',
  add column if not exists modulo_propietario text not null default 'gas_lp',
  add column if not exists facility_id bigint,
  add column if not exists placas text not null default '',
  add column if not exists modelo text not null default '',
  add column if not exists anio integer not null default 2020,
  add column if not exists permiso_cre text not null default '',
  add column if not exists poliza_seguro text not null default '',
  add column if not exists aseguradora text not null default '',
  add column if not exists config_vehicular text not null default 'C2',
  add column if not exists activo boolean not null default true,
  add column if not exists metadata jsonb not null default '{}'::jsonb,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

alter table public.gas_lp_rutas
  add column if not exists tenant_id uuid,
  add column if not exists perfil_id bigint,
  add column if not exists legacy_sqlite_id bigint,
  add column if not exists source text not null default 'supabase',
  add column if not exists modulo_propietario text not null default 'gas_lp',
  add column if not exists origen_facility_id bigint,
  add column if not exists destino_facility_id bigint,
  add column if not exists cp_origen text not null default '',
  add column if not exists cp_destino text not null default '',
  add column if not exists distancia_km numeric not null default 1,
  add column if not exists activo boolean not null default true,
  add column if not exists metadata jsonb not null default '{}'::jsonb,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

alter table public.gas_lp_facturas
  add column if not exists origen_facility_id bigint,
  add column if not exists destino_facility_id bigint,
  add column if not exists chofer_id bigint,
  add column if not exists vehiculo_id bigint,
  add column if not exists ruta_id bigint,
  add column if not exists tipo_comprobante text not null default 'T',
  add column if not exists distancia_km numeric not null default 1,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create unique index if not exists idx_gas_lp_choferes_legacy_unique
  on public.gas_lp_choferes(user_id, perfil_id, legacy_sqlite_id)
  where legacy_sqlite_id is not null;

create unique index if not exists idx_gas_lp_vehiculos_legacy_unique
  on public.gas_lp_vehiculos(user_id, perfil_id, legacy_sqlite_id)
  where legacy_sqlite_id is not null;

create unique index if not exists idx_gas_lp_rutas_legacy_unique
  on public.gas_lp_rutas(user_id, perfil_id, legacy_sqlite_id)
  where legacy_sqlite_id is not null;

create index if not exists idx_gas_lp_choferes_scope
  on public.gas_lp_choferes(user_id, perfil_id, tenant_id, activo);

create index if not exists idx_gas_lp_vehiculos_scope
  on public.gas_lp_vehiculos(user_id, perfil_id, tenant_id, activo);

create index if not exists idx_gas_lp_rutas_scope
  on public.gas_lp_rutas(user_id, perfil_id, tenant_id, activo);

create index if not exists idx_gas_lp_facturas_carta_porte_refs
  on public.gas_lp_facturas(user_id, perfil_id, origen_facility_id, destino_facility_id, vehiculo_id, chofer_id);

alter table public.gas_lp_choferes enable row level security;
alter table public.gas_lp_vehiculos enable row level security;
alter table public.gas_lp_rutas enable row level security;

drop policy if exists ge_gas_lp_choferes_own_rows on public.gas_lp_choferes;
create policy ge_gas_lp_choferes_own_rows on public.gas_lp_choferes
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_choferes.perfil_id
)))
with check (user_id = auth.uid());

drop policy if exists ge_gas_lp_vehiculos_own_rows on public.gas_lp_vehiculos;
create policy ge_gas_lp_vehiculos_own_rows on public.gas_lp_vehiculos
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_vehiculos.perfil_id
)))
with check (user_id = auth.uid());

drop policy if exists ge_gas_lp_rutas_own_rows on public.gas_lp_rutas;
create policy ge_gas_lp_rutas_own_rows on public.gas_lp_rutas
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_rutas.perfil_id
)))
with check (user_id = auth.uid());

commit;
