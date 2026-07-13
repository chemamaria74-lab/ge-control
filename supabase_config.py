"""
supabase_config.py — v2 (thread-safe)

CAMBIOS vs versión anterior:
- Se eliminó el singleton mutable global `_client`.
  El singleton anterior era peligroso: `sb.postgrest.auth(token)` muta el
  objeto compartido, por lo que el JWT del usuario A podía contaminar la
  sesión del usuario B en el mismo worker de Gunicorn.

- `get_supabase()` sigue existiendo para operaciones SIN JWT de usuario
  (operaciones de sistema con la anon key).

- `get_supabase_for_user(token)` es el nuevo helper para operaciones que
  NECESITAN el JWT del usuario (respetar RLS). Crea un cliente fresco
  cada vez; es barato porque no abre sockets hasta el primer request.

- Las variables SUPABASE_URL y SUPABASE_KEY se exportan para que
  `routes/auth.py` pueda importarlas directamente.
"""
import os
import logging
import threading
from functools import lru_cache

import httpx
from supabase import Client, ClientOptions, create_client
from services.observability import supabase_request_hook, supabase_response_hook

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY: str = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
    or ""
).strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Faltan variables de entorno SUPABASE_URL y/o SUPABASE_KEY. "
        "Defínelas en el panel de Render (Environment) o en tu .env local."
    )

# ── Singleton de sistema (anon key, solo para operaciones sin RLS de usuario) ──
_lock: threading.Lock = threading.Lock()
_system_client: Client | None = None
_admin_client: Client | None = None


def _create_supabase_client(key: str) -> Client:
    """Create Supabase client without deprecated PostgREST timeout/verify args."""
    return create_client(
        SUPABASE_URL,
        key,
        options=ClientOptions(httpx_client=httpx.Client(
            timeout=120,
            event_hooks={"request": [supabase_request_hook], "response": [supabase_response_hook]},
        )),
    )


def get_supabase() -> Client:
    """
    Cliente Supabase compartido con la anon key.
    Usar SOLO para operaciones de sistema que no requieren RLS por usuario.
    Para operaciones con JWT de usuario, usar get_supabase_for_user(token).
    """
    global _system_client
    if _system_client is None:
        with _lock:
            if _system_client is None:  # double-checked locking
                _system_client = _create_supabase_client(SUPABASE_KEY)
                logger.info("Cliente Supabase (sistema) inicializado: %s", SUPABASE_URL)
    return _system_client


def get_supabase_admin() -> Client:
    """
    Cliente de servidor para flujos sin sesion de usuario, como portal de operador
    con token firmado. Requiere SUPABASE_SERVICE_ROLE_KEY en Render.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Falta SUPABASE_SERVICE_ROLE_KEY para operaciones de servidor.")
    global _admin_client
    if _admin_client is None:
        with _lock:
            if _admin_client is None:
                _admin_client = _create_supabase_client(SUPABASE_SERVICE_ROLE_KEY)
                logger.info("Cliente Supabase admin inicializado: %s", SUPABASE_URL)
    return _admin_client


def get_supabase_for_user(access_token: str) -> Client:
    """
    Crea un cliente Supabase fresco autenticado con el JWT del usuario.

    Usar en cualquier endpoint donde se necesite respetar las políticas RLS
    (Row Level Security) de Supabase para el usuario autenticado.

    NO reutilizar entre requests: cada request debe llamar esta función
    con su propio token para garantizar aislamiento.

    Ejemplo de uso:
        sb = get_supabase_for_user(access_token)
        rows = sb.table("records").select("*").eq("user_id", uid).execute()
    """
    client = _create_supabase_client(SUPABASE_KEY)
    client.postgrest.auth(access_token)
    return client
