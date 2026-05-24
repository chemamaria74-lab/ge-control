-- GE Control - Gas LP legacy SQLite -> Supabase bridge
-- Fase A/B aditiva: no borra SQLite, no cambia endpoints, no toca timbrado.

begin;

create table if not exists public.gas_lp_facturas (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  facility_id bigint,
  record_uuid text not null default '',
  uuid_sat text not null default '',
  xml_content text not null default '',
  pdf_url text not null default '',
  status text not null default 'Vigente',
  fecha_timbrado timestamptz,
  rfc_receptor text not null default '',
  volumen_litros numeric not null default 0,
  importe numeric not null default 0,
  tipo_comprobante text not null default 'T',
  distancia_km numeric not null default 1,
  chofer_id bigint,
  vehiculo_id bigint,
  ruta_id bigint,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, perfil_id, legacy_sqlite_id)
);

create table if not exists public.gas_lp_facturas_servicio (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  carta_porte_id bigint,
  carta_porte_legacy_sqlite_id bigint,
  uuid_sat text not null default '',
  xml_content text not null default '',
  pdf_url text not null default '',
  status text not null default 'Vigente',
  fecha_timbrado timestamptz,
  rfc_receptor text not null default '',
  importe_flete numeric not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, perfil_id, legacy_sqlite_id)
);

create table if not exists public.gas_lp_choferes (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  nombre text not null,
  rfc text not null default '',
  licencia text not null default '',
  telefono text not null default '',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, perfil_id, legacy_sqlite_id)
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
  placas text not null,
  modelo text not null default '',
  anio integer not null default 2020,
  permiso_cre text not null default '',
  poliza_seguro text not null default '',
  aseguradora text not null default '',
  config_vehicular text not null default 'C2',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, perfil_id, legacy_sqlite_id)
);

create table if not exists public.gas_lp_rutas (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  nombre text not null,
  cp_origen text not null default '',
  cp_destino text not null default '',
  distancia_km numeric not null default 1,
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, perfil_id, legacy_sqlite_id)
);

create table if not exists public.gas_lp_clientes_facturacion (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  legacy_sqlite_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  rfc text not null,
  nombre text not null,
  cp text not null default '',
  regimen_fiscal text not null default '616',
  uso_cfdi text not null default 'S01',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, perfil_id, legacy_sqlite_id)
);

create index if not exists idx_gas_lp_facturas_scope
  on public.gas_lp_facturas(user_id, perfil_id, tenant_id, status, created_at desc);
create index if not exists idx_gas_lp_facturas_legacy
  on public.gas_lp_facturas(user_id, perfil_id, legacy_sqlite_id);
create index if not exists idx_gas_lp_facturas_uuid
  on public.gas_lp_facturas(uuid_sat);

create index if not exists idx_gas_lp_facturas_servicio_scope
  on public.gas_lp_facturas_servicio(user_id, perfil_id, tenant_id, status, created_at desc);
create index if not exists idx_gas_lp_facturas_servicio_legacy
  on public.gas_lp_facturas_servicio(user_id, perfil_id, legacy_sqlite_id);
create index if not exists idx_gas_lp_facturas_servicio_uuid
  on public.gas_lp_facturas_servicio(uuid_sat);

create index if not exists idx_gas_lp_choferes_scope
  on public.gas_lp_choferes(user_id, perfil_id, tenant_id, activo);
create index if not exists idx_gas_lp_vehiculos_scope
  on public.gas_lp_vehiculos(user_id, perfil_id, tenant_id, activo);
create index if not exists idx_gas_lp_rutas_scope
  on public.gas_lp_rutas(user_id, perfil_id, tenant_id, activo);
create index if not exists idx_gas_lp_clientes_scope
  on public.gas_lp_clientes_facturacion(user_id, perfil_id, tenant_id, activo);

alter table public.gas_lp_facturas enable row level security;
alter table public.gas_lp_facturas_servicio enable row level security;
alter table public.gas_lp_choferes enable row level security;
alter table public.gas_lp_vehiculos enable row level security;
alter table public.gas_lp_rutas enable row level security;
alter table public.gas_lp_clientes_facturacion enable row level security;

drop policy if exists ge_gas_lp_facturas_own_rows on public.gas_lp_facturas;
create policy ge_gas_lp_facturas_own_rows on public.gas_lp_facturas
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_facturas.perfil_id
)))
with check (user_id = auth.uid());

drop policy if exists ge_gas_lp_facturas_servicio_own_rows on public.gas_lp_facturas_servicio;
create policy ge_gas_lp_facturas_servicio_own_rows on public.gas_lp_facturas_servicio
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_facturas_servicio.perfil_id
)))
with check (user_id = auth.uid());

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

drop policy if exists ge_gas_lp_clientes_own_rows on public.gas_lp_clientes_facturacion;
create policy ge_gas_lp_clientes_own_rows on public.gas_lp_clientes_facturacion
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_clientes_facturacion.perfil_id
)))
with check (user_id = auth.uid());

commit;
