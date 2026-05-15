-- GE CONTROL - Roles SaaS, empresa asignada y tareas Carta Aporte
-- Ejecutar en Supabase SQL Editor.

alter table public.user_sections
  add column if not exists perfil_id bigint,
  add column if not exists status text not null default 'active';

alter table public.user_sections
  drop constraint if exists user_sections_role_check;

alter table public.user_sections
  add constraint user_sections_role_check
  check (role in ('admin', 'user', 'operador', 'asistente_facturacion', 'planta'));

create index if not exists idx_user_sections_user_section_status
  on public.user_sections(user_id, section, status);

create index if not exists idx_user_sections_perfil
  on public.user_sections(perfil_id);

create table if not exists public.tr_carta_aporte_tasks (
  id bigserial primary key,
  user_id uuid not null,
  perfil_id bigint not null,
  window_start timestamptz not null,
  window_end timestamptz not null,
  status text not null default 'pendiente',
  facturas jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_tr_carta_aporte_tasks_user_perfil
  on public.tr_carta_aporte_tasks(user_id, perfil_id, created_at desc);
