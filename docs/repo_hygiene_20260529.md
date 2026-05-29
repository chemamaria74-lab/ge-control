# Repo hygiene notes - 2026-05-29

## Sirve y se queda

- `main.py`: entrypoint FastAPI.
- `routes/`: endpoints reales de la app.
- `services/`: logica fiscal, PDF, SW Sapien, SAT y transformadores.
- `templates/*.html`: vistas reales que renderiza FastAPI.
- `static/`: CSS, JS, imagenes y marca.
- `migrations/`: cambios de Supabase que deben correrse/replicarse.
- `tests/`: pruebas automatizadas.
- `config/`, `models/`, `utils/`: configuracion, esquemas y utilidades compartidas.

## Estorbaba

- `cfdi.py`, `cliente.py`, `choice.html` en raiz: copias legacy no importadas por la app actual.
- `templates/admin_saas.py` y `templates/transporte_operator_detected.py`: codigo Python dentro de carpeta de HTML.
- `test_cfdi_parser.py` y `test_pipeline.py` en raiz: pruebas utiles, pero fuera de la carpeta `tests/`.
- `.uv-cache/`, `.pytest_cache/`, `__pycache__/`, `.DS_Store`: cache/local noise; no debe subirse.

## Falta robustecer

- Separar en paquetes por dominio cuando baje la urgencia: `gas_lp`, `transporte`, `admin_saas`, `billing`, `sat`.
- Agregar tests e2e/smoke por flujo critico: timbrar Gas LP, descargar PDF/XML/ZIP SAT, Carta Porte traslado, login conciliacion.
- Centralizar validaciones fiscales en una sola capa antes de SW Sapien y usarla en Gas LP, Transporte y Superadmin.
- Documentar variables de entorno reales y ejemplo `.env.example` sin secretos.
- Mantener migrations con nombre fechado y correr `list_migrations`/Supabase antes de deploy.
