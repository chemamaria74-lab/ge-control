# Fase 3 — manifiesto previo de integridad

Fecha: 2026-07-29. Alcance: suscripciones, administradores y acceso por RFC.

No se crearán ni aplicarán migraciones. No habrá conexiones o escrituras en
Supabase productivo. El cliente legado y las cinco filas pendientes permanecen
sin modificación o asignación automática.

| Archivo candidato | SHA-256 previo |
|---|---|
| `models/commercial.py` | `a2ae880fe436c51c3a9931b2c75a7b90bce35f2df7d2e5d9fe0702245734ef86` |
| `services/commercial_rules.py` | `faeb919297455c56aeb081d78531595685e52fd2350a908da2815ecfe2b416d6` |
| `services/commercial_repository.py` | `cf907f77d15db48c9d93565fda9faa3b60b139f2dc7f202a89a2b1d4a2b1bf37` |
| `services/tenant_context.py` | `901865f338db8bd6248bad1760cc6b5e761165ff2bf001a16842753b1e6ce012` |
| `routes/admin_commercial.py` | `350526f88fa4f52e284a30ce92104b4a3fb86828c2cc16f33af73751f72dfcd7` |
| `templates/admin_saas/_commercial.html` | `6db2d4ec7ef444c0fdce20cd3af01293ed5497e3a63959238d73da5c3206dd52` |
| `static/js/admin_saas/60_commercial.js` | `a1818e5321389e1eb446124aa27d76e61090746bbdb4d0662c27f7fe84f96536` |
| `static/css/admin_commercial.css` | `822308e933f93df0da8d5951d233503601f681d49320b99246f712dd9e07b405` |
| `tests/fixtures/phase1_commercial_schema.sql` | `2b0e20a84dfdea6382dc49dd9a9d4eb0c5df8927d44e68dcabad85332fa9f86f` |
| `migrations/phase0_rfc_memberships_deferred_20260728.sql` | `2877921e91204d8573311c826a96a825db07de738cd2bc2e486cc955fb03e7c3` |

La migración diferida de Fase 0 no se modificará en esta fase. Su reemplazo o
consolidación se diseñará únicamente al finalizar todas las fases.

## Cierre

SHA-256 final de archivos preexistentes modificados:

- `models/commercial.py`: `5f6582bd0cb4f7e9ea455309f46e581dec79510872c898551f3953d93e3542a8`
- `services/commercial_rules.py`: `2d064eaaf8059649a4eb65a46a52b05d19108209e6ea15faafaf3e81357f8806`
- `services/commercial_repository.py`: `91bc4b1a5b99f997dafc252cd6a3e5e7d260cb6af350fb2584362b6fb36c086f`
- `services/tenant_context.py`: `7a5dc820dcffbc30d0fe1de04a370a39da6b1bc4b5e39ad7a61a009213604133`
- `routes/admin_commercial.py`: `192279a327697ba032533e87f04ae9b6b008ffad697ce0502fe15fed20cc0ac7`
- `templates/admin_saas/_commercial.html`: `f605d6f447e95e40a7c7ba04fb1dc7ef6a3ea68d5b2f4893df35ff9039885896`
- `static/js/admin_saas/60_commercial.js`: `c1ada862a051f897e969ba910de13dbcd5a195a6be007b2fa9eca6483b726069`
- `static/css/admin_commercial.css`: `0f49943d0944f95bb1080105e98c75575174c43389f4ff0ba96dab876ba50c7a`
- `tests/fixtures/phase1_commercial_schema.sql`: `f5b1f70ee32a91f2ac0fd9aad5e781131487edd21a7e5a4f2294faacd1e8128c`

`migrations/phase0_rfc_memberships_deferred_20260728.sql` conservó exactamente su
hash previo. No se creó ni modificó ningún archivo dentro de `migrations/`.
