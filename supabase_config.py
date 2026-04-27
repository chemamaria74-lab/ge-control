"""Cliente Supabase singleton — todas las credenciales vienen de variables de entorno.

En desarrollo local, carga `.env` automáticamente.
En Render (o cualquier prod), las variables se inyectan desde el panel.
"""
import os
import logging

from supabase import Client, create_client

# Carga .env solo si existe (no rompe en producción si no hay python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Faltan variables de entorno SUPABASE_URL y/o SUPABASE_KEY. "
        "Defínelas en el panel de Render (Environment) o en tu .env local."
    )

_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logger.info("Cliente Supabase inicializado: %s", SUPABASE_URL)


def get_supabase() -> Client:
    """Devuelve el cliente Supabase compartido."""
    return _client
