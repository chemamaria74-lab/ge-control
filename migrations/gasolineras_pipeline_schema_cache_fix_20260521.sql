-- Cierre de contrato DB para pipeline automatico Gasolineras MX.
--
-- 1) La constraint original de coordenadas cortaba Mexico en lat <= 32.0.
--    El padron CRE incluye estaciones reales de Baja California/Tijuana arriba
--    de 32.0, por ejemplo lat 32.47641. Se alinea con el validador Python.
-- 2) Algunas bases staging ya tenian gaso_market_price_snapshots antes de la
--    migracion del pipeline; por eso create table if not exists no agrego
--    ingestion_run_id. Se agrega de forma segura.
-- 3) Se solicita reload de schema a PostgREST para evitar PGRST204 tras DDL.

alter table if exists public.gaso_market_stations
  drop constraint if exists gaso_market_coord_mx;

alter table if exists public.gaso_market_stations
  add constraint gaso_market_coord_mx check (
    lat is null or lng is null or (lat between 14 and 32.8 and lng between -118.8 and -86)
  );

alter table if exists public.gaso_market_price_snapshots
  add column if not exists ingestion_run_id bigint;

create index if not exists idx_gaso_price_snapshots_run_id
  on public.gaso_market_price_snapshots (ingestion_run_id);

notify pgrst, 'reload schema';
