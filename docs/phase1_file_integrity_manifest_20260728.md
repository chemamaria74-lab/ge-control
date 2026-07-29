# Fase 1 — manifiesto previo de integridad

Fecha: 2026-07-28. La copia no contiene `.git` utilizable.

Por instrucción del propietario, Fase 1 no crea ni aplica migraciones. El
esquema se valida solamente en PostgreSQL embebido y las migraciones se
consolidarán al terminar todas las fases.

| Archivo existente candidato | SHA-256 previo |
|---|---|
| `main.py` | `93380583da0972ff2fb32dd6ae32f6b1751f7e6bac62d0bcfa2a14f95838cddf` |
| `templates/admin_saas.html` | `8da58f30a341ab8a21aa832f6b6c375583c7adfd729e9551d806e14745bc4a8a` |
| `services/tenant_context.py` | `901865f338db8bd6248bad1760cc6b5e761165ff2bf001a16842753b1e6ce012` |
| `routes/admin_saas.py` | `915b19a8f0f680e25092cc97f67477f20df9b58b8655da8b05fcce65ad2b638d` |
| `static/css/admin_saas.css` | `3e99541f0ed4775c1313fdde5203b57181286c911e167fb2f0ec6621dc69e9a6` |

Archivos nuevos previstos:

- `models/commercial.py`
- `services/commercial_rules.py`
- `services/commercial_repository.py`
- `routes/admin_commercial.py`
- `templates/admin_saas/_commercial.html`
- `static/js/admin_saas/60_commercial.js`
- `tests/fixtures/phase1_commercial_schema.sql`
- `tests/fixtures/phase1_commercial_scenarios.json`
- `tests/test_phase1_commercial_rules.py`
- `tests/test_phase1_admin_commercial.py`
- `tests/integration/test_phase1_commercial_postgres.py`
- `scripts/phase1_commercial_postgres_evidence.mjs`
- `docs/phase1_commercial_model_20260728.md`

No se modificarán migraciones existentes ni se crearán nuevas en esta fase.

## Cierre

Los únicos archivos preexistentes de la lista anterior que cambiaron fueron
`main.py` y `templates/admin_saas.html`. Además se integró la carga del panel en
`static/js/admin_saas/10_core.js`, cuyo hash final queda registrado en el informe.
`services/tenant_context.py`, `routes/admin_saas.py` y
`static/css/admin_saas.css` permanecieron intactos.

Se crearon todos los archivos previstos. No se creó ninguna migración. El hash
SHA-256 final de `tests/test_phase1_admin_commercial.py` es
`d599b25b5c0c2ebe76f88641a3e8fcd7a1cd820a7ecd060bd64db97269b51cde`.
