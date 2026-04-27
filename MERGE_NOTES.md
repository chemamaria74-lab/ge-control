# Z.Control v3.1 — Notas de Fusión (UI original + seguridad nueva)

Tu interfaz profesional con logo, pestañas Procesar/Facturar y diseño oscuro
queda **intacta** porque vive embebida en `main.py`. Lo único que cambió por
debajo es cómo se autentica el login y cómo se valida la sección.

## Qué cambió (y qué NO cambió)

| Archivo | Cambio | Riesgo de romper UI |
|---|---|---|
| `routes/auth.py` | Reescrito: ahora usa Supabase Auth + `user_sections` | **Ninguno** — misma forma de respuesta |
| `supabase_config.py` | Solo lee `os.environ`; mensaje de error más claro | Ninguno |
| `main.py` | Solo el bloque `if __name__ == "__main__"` lee `PORT` | Ninguno (UI sin tocar) |
| `pyproject.toml` | Agregué `gunicorn`, ajusté versiones | Ninguno |
| `routes/upload.py`, `cfdi.py`, `history.py`, etc. | **No tocados** | Ninguno |

Los 9 routers que importan `verify_token` / `get_current_user` / `require_admin`
siguen funcionando porque esas funciones mantienen exactamente la misma firma.

## Lo que tienes que hacer en Supabase (una sola vez)

1. **Crea la tabla `user_sections`** con esta SQL:

   ```sql
   create table public.user_sections (
     user_id uuid primary key references auth.users(id) on delete cascade,
     section text not null check (section in ('gas_lp', 'transporte')),
     created_at timestamptz default now()
   );

   alter table public.user_sections enable row level security;

   create policy "user_can_read_own_section"
     on public.user_sections for select
     using (auth.uid() = user_id);
   ```

2. **Crea cada usuario** en Authentication → Users (con email + password).
3. **Inserta su sección** en la tabla:

   ```sql
   insert into public.user_sections (user_id, section)
   values ('<UUID-del-usuario>', 'gas_lp');
   ```

> Nota: el formulario de login pide `usuario` y `contraseña`. Para que
> funcione con Supabase, **el "usuario" se interpreta como email**. Si quieres
> dejar literalmente "chema" como usuario, mejor cambia la etiqueta en el HTML
> a "Email" o crea los usuarios con email tipo `chema@tudominio.com`.

## Cómo funciona el multi-tenancy

- Al hacer login, el backend toma el módulo seleccionado en el radio button
  ("Gas LP" o "Transporte") y lo compara con la sección asignada al usuario.
- Si un usuario de `gas_lp` selecciona el radio "Transporte", recibe
  **403** con mensaje claro y no puede entrar.
- Para gatear endpoints específicos por sección, agrega:

  ```python
  from routes.auth import require_section
  from fastapi import Depends

  @router.post("/algo-solo-gas")
  async def x(user_id: str = Depends(require_section("gas_lp"))):
      ...
  ```

## Despliegue en Render — paso a paso

### Subir a GitHub

1. Crea un repo nuevo en GitHub (ej. `z-control`).
2. Desde la carpeta `merged/` (renómbrala como quieras antes):
   ```bash
   git init
   git add .
   git commit -m "Initial: Z.Control v3.1 (UI + Supabase)"
   git remote add origin git@github.com:tu-usuario/z-control.git
   git push -u origin main
   ```
3. Confirma que **NO subiste**: `.env`, `.venv/`, `config/secret.key`,
   `storage/`, `get-pip.py`. El `.gitignore` ya los excluye.

### Crear el Web Service en Render

**Opción A — Manual (panel web):**

1. Render → **New +** → **Web Service** → conecta tu repo.
2. Runtime: **Python 3**.
3. Build Command:
   ```
   pip install uv && uv sync --frozen --no-dev
   ```
4. Start Command (opcional — Render lee el `Procfile`):
   ```
   gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2 --timeout 120
   ```
5. Health Check Path: `/health`
6. **Environment** → Add:
   - `SUPABASE_URL` = `https://TU-PROYECTO.supabase.co`
   - `SUPABASE_KEY` = tu anon key
   - `PYTHON_VERSION` = `3.11.9`

**Opción B — Blueprint:** sube el repo (incluye `render.yaml`) y crea un
Blueprint en Render apuntando al repo. Te pedirá los valores de
`SUPABASE_URL` y `SUPABASE_KEY`.

### Después del primer deploy

- La URL será algo como `https://z-control.onrender.com`.
- Tu UI actual usa rutas relativas (`/api/...`) y mismo origen, así que
  **no hay que tocar nada del frontend** — automáticamente apunta al
  mismo dominio donde corre la API. **No necesitas un Static Site separado.**
- Tu plan free puede dormirse tras 15 min de inactividad. El primer request
  tras dormir tarda ~30s en responder.

## Prueba local antes de subir

```bash
# Desde merged/
cp .env.example .env       # rellena SUPABASE_URL y SUPABASE_KEY
pip install uv
uv sync
uv run python main.py      # http://localhost:8000/login
```

## Seguridad — cosas que tienes que rotar

> **Importante:** tu `.env` original venía dentro del zip que me enviaste.
> Aunque la `SUPABASE_KEY` sea la `anon` (pensada para ser pública), por
> higiene te recomiendo:
>
> 1. **NO** subir nunca `.env` a GitHub (ya está en `.gitignore`).
> 2. Si crees que la clave anon estuvo expuesta más allá del zip, en
>    Supabase: Project Settings → API → "Reset anon key".

## Estructura final

```
merged/                          ← renómbralo a "z-control" antes de subir
├── main.py                      ← UI + endpoints (UI INTACTA)
├── supabase_config.py           ← env-only
├── supabase_client.py / cliente.py
├── schemas.py
├── routes/
│   ├── auth.py                  ← reescrito: Supabase + secciones
│   ├── upload.py, cfdi.py, ...  ← intactos
├── services/
│   ├── database.py              ← intacto (SQLite local p/ settings/historial)
│   └── ...
├── models/, utils/, config/, static/
├── pyproject.toml               ← + gunicorn, versiones limpiadas
├── uv.lock
├── Procfile                     ← arranque para Render
├── render.yaml                  ← blueprint opcional
├── .env.example                 ← plantilla
├── .gitignore                   ← excluye .env, .venv, secret.key, storage/
└── MERGE_NOTES.md               ← este archivo
```
