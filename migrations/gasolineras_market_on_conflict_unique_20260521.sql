-- Permite que PostgREST/Supabase use upsert(..., on_conflict="permiso_cre")
-- en gaso_market_stations.
--
-- La migracion previa tenia un indice unico parcial:
--   unique (permiso_cre) where permiso_cre <> ''
-- Ese indice protege datos validos, pero PostgreSQL no lo puede inferir para
-- ON CONFLICT (permiso_cre) emitido por PostgREST, provocando error 42P10.
--
-- El pipeline automatico siempre normaliza permiso_cre a un valor no vacio:
-- CRE si existe o fallback GEO-lat-lng para registros georreferenciados.
create unique index if not exists idx_gaso_market_permiso_cre_on_conflict
  on public.gaso_market_stations (permiso_cre);
