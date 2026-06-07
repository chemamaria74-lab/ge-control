# routes/transporte.py
# Compatibility entrypoint for the Transporte API router.
# The implementation lives in routes/transporte_mod/ to keep backend areas smaller.

from routes.transporte_mod import router
from routes.transporte_mod.core import *  # noqa: F401,F403
from routes.transporte_mod import operador as _operador_module


def _operador_context(token_plain: str):
    # Preserve tests and integrations that monkeypatch routes.transporte.get_supabase_admin.
    _operador_module.get_supabase_admin = get_supabase_admin
    return _operador_module._operador_context(token_plain)


def _operador_meta(sb, acc: dict) -> dict:
    return _operador_module._operador_meta(sb, acc)


__all__ = [name for name in globals() if not name.startswith("__")]
