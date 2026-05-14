-- Z Control - Modulo Gasolineras
-- Ejecutar en Supabase SQL Editor.

-- Permite asignar el modulo a usuarios:
-- insert into user_sections (user_id, section) values ('UUID_DEL_USUARIO', 'gasolineras')
-- on conflict do nothing;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_sections_user_section
  ON public.user_sections (user_id, section);

CREATE TABLE IF NOT EXISTS public.gaso_settings (
  id          bigserial PRIMARY KEY,
  user_id     text NOT NULL,
  perfil_id   bigint,
  data        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gaso_settings_user_perfil
  ON public.gaso_settings (user_id, perfil_id);

CREATE TABLE IF NOT EXISTS public.gaso_estaciones (
  id              bigserial PRIMARY KEY,
  user_id          text NOT NULL,
  perfil_id        bigint,
  nombre           text NOT NULL DEFAULT '',
  permiso          text NOT NULL DEFAULT '',
  rfc              text NOT NULL DEFAULT '',
  codigo_postal    text NOT NULL DEFAULT '',
  lat              numeric,
  lng              numeric,
  activo           boolean NOT NULL DEFAULT true,
  data             jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gaso_estaciones_user_perfil
  ON public.gaso_estaciones (user_id, perfil_id);

CREATE TABLE IF NOT EXISTS public.gaso_cfdi (
  id            bigserial PRIMARY KEY,
  user_id        text NOT NULL,
  perfil_id      bigint,
  estacion_id    bigint REFERENCES public.gaso_estaciones(id) ON DELETE SET NULL,
  uuid_sat       text NOT NULL DEFAULT '',
  xml_content    text NOT NULL DEFAULT '',
  pdf_path       text NOT NULL DEFAULT '',
  status         text NOT NULL DEFAULT 'vigente',
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gaso_cfdi_user_perfil
  ON public.gaso_cfdi (user_id, perfil_id);
