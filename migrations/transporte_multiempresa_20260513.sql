-- Z Control - Transporte multiempresa por usuario
-- Ejecutar en Supabase SQL Editor.

ALTER TABLE public.tr_choferes
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_vehiculos
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_rutas
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_clientes
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_viajes
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_cfdi
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_settings
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_covol_reports
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_facturas_servicio
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

ALTER TABLE public.tr_facturas_servicio_cartas
  ADD COLUMN IF NOT EXISTS perfil_id bigint;

CREATE INDEX IF NOT EXISTS idx_tr_choferes_user_perfil
  ON public.tr_choferes (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_vehiculos_user_perfil
  ON public.tr_vehiculos (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_rutas_user_perfil
  ON public.tr_rutas (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_clientes_user_perfil
  ON public.tr_clientes (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_viajes_user_perfil
  ON public.tr_viajes (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_cfdi_user_perfil
  ON public.tr_cfdi (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_fact_serv_user_perfil
  ON public.tr_facturas_servicio (user_id, perfil_id);

CREATE INDEX IF NOT EXISTS idx_tr_fact_serv_cartas_user_perfil
  ON public.tr_facturas_servicio_cartas (user_id, perfil_id);
