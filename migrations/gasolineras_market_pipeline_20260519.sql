-- GE CONTROL - Gasolineras inteligencia de mercado real
-- Ejecutar en Supabase SQL Editor despues de gasolineras_modulo_20260514.sql.

alter table if exists public.gaso_market_stations
  add column if not exists geohash text not null default '',
  add column if not exists last_seen_at timestamptz,
  add column if not exists inactive_detected_at timestamptz,
  add column if not exists source_period text not null default '',
  add column if not exists source_url text not null default '';

create unique index if not exists idx_gaso_market_permiso_unique
  on public.gaso_market_stations (permiso_cre)
  where permiso_cre <> '';

create index if not exists idx_gaso_market_bbox_active
  on public.gaso_market_stations (activa, lat, lng);

create index if not exists idx_gaso_market_estado_municipio
  on public.gaso_market_stations (estado, municipio);

create table if not exists public.gaso_market_price_snapshots (
  id bigserial primary key,
  market_station_id bigint references public.gaso_market_stations(id) on delete cascade,
  ingestion_run_id bigint,
  permiso_cre text not null default '',
  producto text not null check (producto in ('regular', 'premium', 'diesel')),
  precio numeric not null default 0,
  fuente text not null default 'CRE_DATOS_ABIERTOS',
  source_period text not null default '',
  observed_at timestamptz not null default now(),
  ingested_at timestamptz not null default now(),
  data jsonb not null default '{}'::jsonb
);

create index if not exists idx_gaso_market_price_permiso_producto
  on public.gaso_market_price_snapshots (permiso_cre, producto, observed_at desc);

create table if not exists public.gaso_ingestion_runs (
  id bigserial primary key,
  source text not null,
  status text not null default 'running',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  rows_seen integer not null default 0,
  rows_valid integer not null default 0,
  rows_rejected integer not null default 0,
  rows_upserted integer not null default 0,
  error text not null default '',
  data jsonb not null default '{}'::jsonb
);

alter table public.gaso_market_stations enable row level security;
alter table public.gaso_market_price_snapshots enable row level security;
alter table public.gaso_ingestion_runs enable row level security;

drop policy if exists gaso_market_public_read_auth on public.gaso_market_stations;
create policy gaso_market_public_read_auth
  on public.gaso_market_stations for select to authenticated
  using (true);

drop policy if exists gaso_market_prices_read_auth on public.gaso_market_price_snapshots;
create policy gaso_market_prices_read_auth
  on public.gaso_market_price_snapshots for select to authenticated
  using (true);

drop policy if exists gaso_ingestion_admin_read on public.gaso_ingestion_runs;
create policy gaso_ingestion_admin_read
  on public.gaso_ingestion_runs for select to authenticated
  using (true);
