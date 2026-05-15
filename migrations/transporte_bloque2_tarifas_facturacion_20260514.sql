-- GE CONTROL - Transporte Bloque 2: tarifas e impuestos configurables
-- Ejecutar en Supabase SQL Editor antes de timbrar facturas de servicio con retenciones.

alter table if exists public.tr_facturas_servicio
  add column if not exists retencion numeric not null default 0,
  add column if not exists iva_tasa numeric not null default 0.16,
  add column if not exists retencion_tasa numeric not null default 0.04,
  add column if not exists aplica_iva boolean not null default true,
  add column if not exists aplica_retencion boolean not null default false,
  add column if not exists calculo_json jsonb not null default '{}'::jsonb;

alter table if exists public.tr_tarifas
  add column if not exists observaciones text not null default '';

comment on table public.tr_tarifas is
  'Tarifas configurables por usuario/perfil para servicio de transporte: cliente, ruta, producto, tipo de cálculo e impuestos.';

comment on column public.tr_tarifas.regla_calculo is
  'Tipo de tarifa: litros, kilos, distancia/km, viaje o manual.';

comment on column public.tr_facturas_servicio.calculo_json is
  'Detalle de cálculo servidor: tarifas aplicadas, subtotal, IVA, retención y total por viaje.';
