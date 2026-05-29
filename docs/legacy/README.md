# Legacy files moved from root

These files are preserved for comparison only. They were uploaded into the
repository root or the `templates/` directory, but the running app uses the
current modules under `routes/`, `services/`, `config/`, and `templates/*.html`.

- `root_uploads/cfdi.py`: legacy CFDI route copy; active code is `routes/cfdi.py`.
- `root_uploads/cliente.py`: legacy client config helper; active code is `config/cliente.py` and `supabase_config.py`.
- `root_uploads/choice.html`: legacy root template; active code is `templates/choice.html`.
- `templates_py/*.py`: Python route copies that were sitting inside `templates/`; active route modules live in `routes/`.
