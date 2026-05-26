# Gas LP Excel Facilities Import Runbook

## Purpose

Import operational Gas LP installations from an Excel matrix into `public.user_facilities` without manual capture.

The importer is designed for staging QA and future onboarding:

- dry-run first;
- idempotent by `user_id + perfil_id + num_permiso` with fallback to `clave_instalacion`/`nombre`;
- no hardcoded company assignment;
- no deletes;
- preserves the original parsed row in `import_payload`.

## Current Excel Shape

The file `Informacion JSON Plantas (1).xlsx` has one matrix sheet:

- columns: installations/plants/stations;
- rows: attributes like permit, SAT activity, installation key, capacity, tank/dispensers, calibration and coordinates.

Detected fields include:

- `Tipo de Permiso CRE`
- `Actividad SAT`
- `Clave Instalación`
- `Núm. Permiso CRE (distribución)`
- `Descripción Instalación`
- `Temperatura Default (°C)`
- `Núm. Tanques`
- `Núm. Dispensarios`
- `Clave del Tanque`
- tank capacity fields
- calibration fields
- latitude/longitude

## Target Table

Use the existing `public.user_facilities` table.

Reason: it is already consumed by Gas LP UI, controls/history flows, facility selector and configuration.

The additive migration `migrations/gas_lp_facility_import_metadata_20260524.sql` adds import metadata:

- `updated_at`
- `import_source`
- `import_source_file`
- `import_source_hash`
- `import_batch_id`
- `import_payload`

## Profile Mapping

The Excel currently does not include an explicit company/profile column. Do not infer production ownership silently.

Use a mapping JSON:

```json
{
  "facility_to_perfil": {
    "Planta Alfa Tepusco": 5
  },
  "permit_to_perfil": {
    "LP/14442/DIST/PLA/2016": 5
  },
  "regex_to_perfil": [
    { "pattern": "Alfa|Ejidal|Teocaltiche", "perfil_id": 5 }
  ]
}
```

If only one active profile exists for the owner user, the script can use that profile automatically.

## Dry Run

```bash
SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
python scripts/import_gas_lp_facilities_from_excel.py \
  "/path/to/Informacion JSON Plantas (1).xlsx" \
  --owner-user-id "<auth-user-id>" \
  --profile-map-json "/path/to/profile_map.json"
```

## Apply

```bash
SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
python scripts/import_gas_lp_facilities_from_excel.py \
  "/path/to/Informacion JSON Plantas (1).xlsx" \
  --owner-user-id "<auth-user-id>" \
  --profile-map-json "/path/to/profile_map.json" \
  --apply
```

## Validation

After import:

```sql
select perfil_id, count(*)
from public.user_facilities
where import_source = 'excel_gas_lp_facilities'
group by perfil_id
order by perfil_id;
```

Then validate in UI:

- Gas LP admin login;
- select company/profile;
- Configuración -> Instalaciones;
- Procesar -> selector de instalación.

## GO / NO GO

GO to run in staging only after:

- migration applied;
- profile mapping reviewed;
- dry-run preview shows expected perfil for each installation;
- no unmapped rows;
- coordinates warnings are acceptable.

NO GO for production until:

- accountant/PAC validates `Actividad SAT` values (`EXP` vs current UI `EXO` mapping);
- profile mapping is provided by client or onboarding admin;
- legacy open policies are closed after Gas LP Supabase-only QA.
