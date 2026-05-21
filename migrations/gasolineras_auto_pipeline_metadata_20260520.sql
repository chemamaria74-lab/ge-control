-- Metadata for the automatic Gasolineras MX CRE/CNE ingestion pipeline.
-- Safe, additive migration. Existing rows keep working through data JSON.

alter table if exists public.gaso_ingestion_runs
  add column if not exists source_url text,
  add column if not exists source_period text,
  add column if not exists source_hash text,
  add column if not exists row_count integer;

alter table if exists public.gaso_market_price_snapshots
  add column if not exists delta_anterior numeric;

create index if not exists idx_gaso_ingestion_runs_source_period
  on public.gaso_ingestion_runs (source, source_period, started_at desc);

create index if not exists idx_gaso_price_snapshots_permiso_producto_time
  on public.gaso_market_price_snapshots (permiso_cre, producto, observed_at desc);
