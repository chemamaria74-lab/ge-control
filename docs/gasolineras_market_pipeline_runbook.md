# Runbook Pipeline Gasolineras MX

## Objetivo

Mantener el padrón nacional de estaciones, precios CRE y estatus CNE actualizado sin depender de un CSV permanente.

## Fuentes

- CRE estaciones: `https://publicacionexterna.azurewebsites.net/publicaciones/places`
- CRE precios: `https://publicacionexterna.azurewebsites.net/publicaciones/prices`
- CNE permisos mensual: `https://repodatos.atdt.gob.mx/api_update/cne/petroliferos/pl_per_vig_MMYYYY.csv`
- Fallback manual opcional: `GASO_MARKET_CSV_URL`

## Comandos

```bash
uv run python scripts/update_gasolineras_market.py --dry-run --limit 200
uv run python scripts/update_gasolineras_market.py
uv run python scripts/update_gasolineras_prices.py --dry-run --limit 500
uv run python scripts/update_gasolineras_prices.py
```

Para escribir en Supabase se requieren:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

No usar la service role key en frontend ni imprimirla en logs.

## Persistencia

- `gaso_market_stations`: upsert por `permiso_cre`, coordenadas Mexico validadas, `source_period`, `source_url`, `last_seen_at`.
- `gaso_market_price_snapshots`: snapshots por permiso/producto con `delta_anterior` si existe precio previo.
- `gaso_ingestion_runs`: bitacora con `source_url`, `source_period`, `source_hash`, `row_count`, conteos y errores.

## Fallback y seguridad operativa

- Si CNE mensual no existe todavia, la corrida continua con CRE y registra CNE como fuente opcional faltante.
- Si CRE places o CRE prices fallan, la corrida falla y no borra datos previos.
- No se insertan datos fake.
- El dashboard muestra ultima corrida, ultima version valida y estado real del dataset.

## Scheduler

- `.github/workflows/update_gasolineras_market.yml`: diario.
- `.github/workflows/update_gasolineras_prices.yml`: cada 4 horas.

## Verificacion

1. Revisar workflow exitoso.
2. Consultar `/api/gaso/market/status` con usuario autorizado.
3. Confirmar `last_valid_version_available=true`.
4. Confirmar `stations_loaded > 0`.
5. Confirmar que el dashboard ya no muestre dataset vacio cuando hay filas reales.
