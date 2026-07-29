# Fase 2 — manifiesto previo de integridad

Fecha: 2026-07-28. Alcance: CRM comercial operativo local.

No se crearán ni aplicarán migraciones. No se escribirá en Supabase productivo.
El esquema de prueba continuará dentro de `tests/fixtures`.

| Archivo existente candidato | SHA-256 previo |
|---|---|
| `models/commercial.py` | `2e46fde11fd30df675125347bbba618dec9ef548a72f16f2dbe7bd7f79311c8a` |
| `services/commercial_rules.py` | `1a4a34ff716f32c4e073a9b86df3315b7204b96b2f4cb7778dda6a7d96e9e5d9` |
| `services/commercial_repository.py` | `f3d8b01a69054ace86243d2880049df317f689528054571479fbdb8c6d379529` |
| `routes/admin_commercial.py` | `9eeddb9ad9f0e041aaa2f24c44899d56675540d9eec917f41f4b1f240f9454bb` |
| `templates/admin_saas/_commercial.html` | `193675a73414dcb544ae55196c90737cea76cb55ec54df4227b1c7503c947e7b` |
| `static/js/admin_saas/60_commercial.js` | `bc02fd09bc70bdd31bf2d19785fd38631fce0825dcb8aa770a726cebf74d058d` |
| `static/css/admin_commercial.css` | `07e80a5f3c4a13690a2c26631ee529ca6db9e01c51eaf3a6da80fc1daac5aac0` |
| `tests/fixtures/phase1_commercial_schema.sql` | `5723d59397406790a4009998b0f6333a9ba97eba4fb26b058c4b38770746cd2c` |

Archivos nuevos previstos:

- `tests/test_phase2_crm_rules.py`
- `tests/test_phase2_admin_crm.py`
- `tests/integration/test_phase2_crm_postgres.py`
- `scripts/phase2_crm_postgres_evidence.mjs`
- `docs/phase2_crm_operativo_20260728.md`

## Cierre

Archivos preexistentes modificados y SHA-256 final:

- `models/commercial.py`: `a2ae880fe436c51c3a9931b2c75a7b90bce35f2df7d2e5d9fe0702245734ef86`
- `services/commercial_rules.py`: `faeb919297455c56aeb081d78531595685e52fd2350a908da2815ecfe2b416d6`
- `services/commercial_repository.py`: `cf907f77d15db48c9d93565fda9faa3b60b139f2dc7f202a89a2b1d4a2b1bf37`
- `routes/admin_commercial.py`: `350526f88fa4f52e284a30ce92104b4a3fb86828c2cc16f33af73751f72dfcd7`
- `templates/admin_saas/_commercial.html`: `6db2d4ec7ef444c0fdce20cd3af01293ed5497e3a63959238d73da5c3206dd52`
- `static/js/admin_saas/60_commercial.js`: `a1818e5321389e1eb446124aa27d76e61090746bbdb4d0662c27f7fe84f96536`
- `static/css/admin_commercial.css`: `822308e933f93df0da8d5951d233503601f681d49320b99246f712dd9e07b405`
- `tests/fixtures/phase1_commercial_schema.sql`: `2b0e20a84dfdea6382dc49dd9a9d4eb0c5df8927d44e68dcabad85332fa9f86f`

No se modificó ningún archivo dentro de `migrations/`.
