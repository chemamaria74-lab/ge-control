# Fase 0 — manifiesto previo de integridad

Fecha de captura: 2026-07-28  
Alcance: seguridad y línea base del Superadmin/Transporte.  
Estado Git: la copia de trabajo no contiene un `.git` utilizable.

Este manifiesto se creó antes de modificar código funcional. Los hashes son
SHA-256 del contenido recibido al iniciar la Fase 0.

| Archivo existente candidato | SHA-256 previo |
|---|---|
| `main.py` | `6f820a2e571c48fa927a5a63e2f1e4cf43c10c25fb3e14994174a1a71909921a` |
| `routes/admin_saas.py` | `75639fe5176348fd0d106673dc12cc6ff1f46366f138ec32833e4a10bb6b8068` |
| `routes/admin_saas_scope_guard.py` | `7338fbab0544b067af5c553c62ed86744459f1c9e58bbdce33879a17da1a65d5` |
| `services/tenant_context.py` | `9dc6bfdcccfd5025a9a633a87cd069d125d380a55076d2251f141b1f5b2f8446` |
| `routes/auth.py` | `7f472322c4b4676b242e705ff310d708dc0505c215e58dabedcc3d2eaa51594c` |

Archivos nuevos previstos (ausentes al capturar este manifiesto):

- `migrations/phase0_subscription_scope_deferred_20260728.sql`
- `migrations/phase0_transport_rls_deferred_20260728.sql`
- `tests/fixtures/phase0_tenant_isolation.json`
- `tests/test_phase0_tenant_context.py`
- `tests/test_phase0_admin_saas_security.py`
- `tests/integration/test_phase0_rls_postgres.py`
- `scripts/phase0_rls_evidence.py`
- `docs/phase0_security_baseline_20260728.md`

Reglas de revisión:

1. Ninguna migración de este alcance se aplica automáticamente.
2. Los archivos SQL nuevos deben declarar `DEFERRED / NO APLICAR`.
3. El informe final incluirá hashes posteriores de todos los archivos
   modificados o creados.
4. Si el alcance cambia, se añadirá el archivo al informe final y se conservará
   su hash previo cuando ya existiera.

## Hashes posteriores a Fase 0

| Archivo | SHA-256 posterior |
|---|---|
| `main.py` | `93380583da0972ff2fb32dd6ae32f6b1751f7e6bac62d0bcfa2a14f95838cddf` |
| `routes/admin_saas.py` | `915b19a8f0f680e25092cc97f67477f20df9b58b8655da8b05fcce65ad2b638d` |
| `routes/admin_saas_scope_guard.py` | `c66bee2579bcfc6062098563fedeb38b16bf532fb84bb248401845d3ee788194` |
| `services/tenant_context.py` | `901865f338db8bd6248bad1760cc6b5e761165ff2bf001a16842753b1e6ce012` |
| `docs/phase0_security_baseline_20260728.md` | `6f02dd5c76d14a74d1d72decfa5915edb37707029fc4c6e5f6d067aaaf326f94` |
| `migrations/phase0_rfc_memberships_deferred_20260728.sql` | `2877921e91204d8573311c826a96a825db07de738cd2bc2e486cc955fb03e7c3` |
| `migrations/phase0_transport_scope_additive_deferred_20260728.sql` | `53f1a82da78676eee0c2b20bb46db31d2bf5e4f781cd8d8436579a86223ad1db` |
| `migrations/phase0_transport_rls_enforcement_deferred_20260728.sql` | `92d538f82f673915dca43a4c8268db2dbff588fb22e58cdf5670cfbcac993c05` |
| `tests/fixtures/phase0_tenant_isolation.json` | `5a773a3843825d9bb8db81638a25e9e7174232d53540d2da36f93568b039addb` |
| `scripts/phase0_rls_evidence.mjs` | `09cb527d17f91a70ec0a20d1a736e5a915f456ba3c482d6de88e250c67ef7fbe` |
| `scripts/phase0_migration_smoke.mjs` | `eb93bd779a5e7ded902faa341d184d7493de722852743d04396b9d8c2071e0d3` |
| `tests/test_phase0_tenant_context.py` | `9d4ddb6e546b38503b6e5d59d98e7eb275de6c4cd8ae3eb24eaea322729db0bc` |
| `tests/test_phase0_admin_saas_security.py` | `8518be1af76b38f1f1e9eea9c39862b3f7c23f0ffde6005ae4d4d8d62f70cf41` |
| `tests/integration/test_phase0_rls_postgres.py` | `78ba1351dc6352fb9b29c9fdd036df8ab28cca9efcc64682210ce2056f772e7c` |

El archivo de manifiesto no incluye su propio hash para evitar una referencia
circular. Su integridad debe verificarse desde el informe externo de entrega.
