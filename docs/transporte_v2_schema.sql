-- Transporte v2 Fase 1
-- SQL no destructivo. No ejecutar sin validar en ambiente controlado.
-- Crea tablas nuevas transporte_v2_*; no toca Gas LP, /api/tr/* legacy ni tablas tr_*.

create table if not exists public.transporte_v2_clientes (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  nombre text not null,
  rfc text,
  cp text,
  regimen_fiscal text,
  uso_cfdi text,
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_operadores (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  nombre text not null,
  rfc_figura text,
  licencia text,
  telefono text,
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_vehiculos (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  alias text,
  placas text not null,
  config_vehicular text,
  modelo text,
  anio int,
  permiso_sct text,
  num_permiso_sct text,
  aseguradora_rc text,
  poliza_rc text,
  aseguradora_medio_ambiente text,
  poliza_medio_ambiente text,
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_productos (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  descripcion text not null,
  clave_producto text,
  clave_subproducto text,
  unidad text default 'LTR',
  material_peligroso boolean default false,
  clave_material_peligroso text,
  embalaje text,
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_rutas (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  nombre text not null,
  origen text,
  destino text,
  cp_origen text,
  cp_destino text,
  distancia_km numeric default 0,
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_viajes (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  cliente_id bigint,
  operador_id bigint,
  vehiculo_id bigint,
  producto_id bigint,
  ruta_id bigint,
  origen text,
  destino text,
  volumen_litros numeric default 0,
  peso_kg numeric default 0,
  fecha_salida timestamptz,
  fecha_llegada_estimada timestamptz,
  estatus text not null default 'borrador',
  observaciones text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_documentos_cliente (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  viaje_id bigint,
  tipo_documento text not null,
  nombre_archivo text not null,
  storage_bucket text,
  storage_path text,
  content_type text,
  size_bytes bigint,
  metadata jsonb not null default '{}'::jsonb,
  uploaded_by text,
  created_at timestamptz not null default now()
);

create table if not exists public.transporte_v2_auditoria (
  id bigserial primary key,
  user_id text not null,
  perfil_id bigint,
  entidad text not null,
  entidad_id bigint,
  accion text not null,
  detalle jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_transporte_v2_viajes_user_perfil
  on public.transporte_v2_viajes(user_id, perfil_id, created_at desc);

create index if not exists idx_transporte_v2_documentos_viaje
  on public.transporte_v2_documentos_cliente(user_id, perfil_id, viaje_id, created_at desc);

create index if not exists idx_transporte_v2_clientes_user_perfil
  on public.transporte_v2_clientes(user_id, perfil_id, activo);

create index if not exists idx_transporte_v2_operadores_user_perfil
  on public.transporte_v2_operadores(user_id, perfil_id, activo);

create index if not exists idx_transporte_v2_vehiculos_user_perfil
  on public.transporte_v2_vehiculos(user_id, perfil_id, activo);

create index if not exists idx_transporte_v2_productos_user_perfil
  on public.transporte_v2_productos(user_id, perfil_id, activo);

create index if not exists idx_transporte_v2_rutas_user_perfil
  on public.transporte_v2_rutas(user_id, perfil_id, activo);

alter table public.transporte_v2_clientes enable row level security;
alter table public.transporte_v2_operadores enable row level security;
alter table public.transporte_v2_vehiculos enable row level security;
alter table public.transporte_v2_productos enable row level security;
alter table public.transporte_v2_rutas enable row level security;
alter table public.transporte_v2_viajes enable row level security;
alter table public.transporte_v2_documentos_cliente enable row level security;
alter table public.transporte_v2_auditoria enable row level security;

create policy transporte_v2_clientes_user_policy on public.transporte_v2_clientes
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_operadores_user_policy on public.transporte_v2_operadores
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_vehiculos_user_policy on public.transporte_v2_vehiculos
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_productos_user_policy on public.transporte_v2_productos
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_rutas_user_policy on public.transporte_v2_rutas
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_viajes_user_policy on public.transporte_v2_viajes
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_documentos_user_policy on public.transporte_v2_documentos_cliente
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

create policy transporte_v2_auditoria_user_policy on public.transporte_v2_auditoria
  for all using (user_id = auth.uid()::text) with check (user_id = auth.uid()::text);

grant select, insert, update on public.transporte_v2_clientes to authenticated;
grant select, insert, update on public.transporte_v2_operadores to authenticated;
grant select, insert, update on public.transporte_v2_vehiculos to authenticated;
grant select, insert, update on public.transporte_v2_productos to authenticated;
grant select, insert, update on public.transporte_v2_rutas to authenticated;
grant select, insert, update on public.transporte_v2_viajes to authenticated;
grant select, insert, update on public.transporte_v2_documentos_cliente to authenticated;
grant select, insert on public.transporte_v2_auditoria to authenticated;

grant usage, select on sequence public.transporte_v2_clientes_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_operadores_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_vehiculos_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_productos_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_rutas_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_viajes_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_documentos_cliente_id_seq to authenticated;
grant usage, select on sequence public.transporte_v2_auditoria_id_seq to authenticated;
