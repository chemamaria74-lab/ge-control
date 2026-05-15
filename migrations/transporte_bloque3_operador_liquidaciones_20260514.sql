-- GE CONTROL - Transporte Bloque 3: operador simple y liquidaciones/quincenas
-- Ejecutar en Supabase SQL Editor antes de usar export, pagos y ajustes de liquidación.

alter table if exists public.tr_liquidaciones
  add column if not exists periodo_inicio timestamptz,
  add column if not exists periodo_fin timestamptz,
  add column if not exists comision_extra numeric not null default 0,
  add column if not exists descuentos numeric not null default 0,
  add column if not exists metodo_pago text not null default '',
  add column if not exists referencia_pago text not null default '',
  add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table if exists public.tr_gastos_viaje
  add column if not exists paid_at timestamptz,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table if exists public.tr_notificaciones
  add column if not exists read_at timestamptz;

create index if not exists idx_tr_liquidaciones_chofer_periodo
  on public.tr_liquidaciones(user_id, perfil_id, chofer_id, periodo, status);

create index if not exists idx_tr_notificaciones_status
  on public.tr_notificaciones(user_id, perfil_id, status, created_at desc);

comment on column public.tr_liquidaciones.periodo is
  'Periodo lógico: YYYY-MM para mensual o YYYY-MM-Q1/YYYY-MM-Q2 para quincenas.';

comment on column public.tr_liquidaciones.metodo_pago is
  'Método operativo de pago: efectivo, transferencia, cheque u otro.';
