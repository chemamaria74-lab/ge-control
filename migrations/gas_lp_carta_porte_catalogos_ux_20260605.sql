-- GE Control - Gas LP Carta Porte UX catalog support
-- Crea solamente los catalogos faltantes para ubicaciones y mercancias.
-- No toca XML, timbrado, facturas ni cancelaciones.

begin;

create table if not exists public.gas_lp_ubicaciones_carta_porte (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  alias text not null default '',
  tipo text not null default 'ambos',
  rfc text not null default '',
  nombre text not null default '',
  codigo_postal text not null default '',
  estado text not null default '',
  municipio text not null default '',
  localidad_colonia text not null default '',
  calle text not null default '',
  numero_exterior text not null default '',
  numero_interior text not null default '',
  pais text not null default 'MEX',
  id_ubicacion text not null default '',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gas_lp_mercancias_carta_porte (
  id bigserial primary key,
  user_id uuid not null,
  tenant_id uuid,
  perfil_id bigint,
  source text not null default 'supabase',
  modulo_propietario text not null default 'gas_lp',
  alias text not null default '',
  bienes_transp text not null default '',
  descripcion text not null default '',
  clave_unidad text not null default 'LTR',
  unidad text not null default 'L',
  factor_kg_litro numeric not null default 0.54,
  material_peligroso boolean not null default true,
  clave_material_peligroso text not null default '',
  embalaje text not null default '',
  descripcion_embalaje text not null default '',
  activo boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_gas_lp_ubicaciones_cp_scope
  on public.gas_lp_ubicaciones_carta_porte(user_id, perfil_id, tenant_id, activo);

create index if not exists idx_gas_lp_mercancias_cp_scope
  on public.gas_lp_mercancias_carta_porte(user_id, perfil_id, tenant_id, activo);

alter table public.gas_lp_ubicaciones_carta_porte enable row level security;
alter table public.gas_lp_mercancias_carta_porte enable row level security;

drop policy if exists ge_gas_lp_ubicaciones_cp_own_rows on public.gas_lp_ubicaciones_carta_porte;
create policy ge_gas_lp_ubicaciones_cp_own_rows on public.gas_lp_ubicaciones_carta_porte
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_ubicaciones_carta_porte.perfil_id
)))
with check (user_id = auth.uid());

drop policy if exists ge_gas_lp_mercancias_cp_own_rows on public.gas_lp_mercancias_carta_porte;
create policy ge_gas_lp_mercancias_cp_own_rows on public.gas_lp_mercancias_carta_porte
for all to authenticated
using (user_id = auth.uid() and (perfil_id is null or exists (
  select 1 from public.user_sections us
  where us.user_id = auth.uid()
    and us.status = 'active'
    and us.section = 'gas_lp'
    and us.perfil_id = gas_lp_mercancias_carta_porte.perfil_id
)))
with check (user_id = auth.uid());

commit;
