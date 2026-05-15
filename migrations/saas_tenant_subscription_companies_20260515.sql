-- GE CONTROL - Modelo SaaS tenant/subscription/companies
-- Ejecutar en Supabase SQL Editor antes de vender por suscripción.

create table if not exists public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null default '',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
  id bigserial primary key,
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  plan_name text not null default 'Básico',
  max_companies integer,
  status text not null default 'active',
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status in ('active', 'trialing', 'past_due', 'canceled', 'expired')),
  check (max_companies is null or max_companies >= 0)
);

create table if not exists public.companies (
  id bigint primary key,
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  name text not null,
  rfc text not null default '',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_sections
  add column if not exists tenant_id uuid references public.tenants(id),
  add column if not exists perfil_id bigint,
  add column if not exists status text not null default 'active';

alter table public.perfiles_empresa
  add column if not exists tenant_id uuid references public.tenants(id);

create index if not exists idx_user_sections_tenant
  on public.user_sections(tenant_id, user_id, section);

create index if not exists idx_companies_tenant_active
  on public.companies(tenant_id, active);

create index if not exists idx_subscriptions_tenant_status
  on public.subscriptions(tenant_id, status);

create index if not exists idx_perfiles_empresa_tenant_active
  on public.perfiles_empresa(tenant_id, activo);

-- Backfill recomendado:
-- 1. Crear un tenant por cliente.
-- 2. Asignar user_sections.tenant_id.
-- 3. Asignar perfiles_empresa.tenant_id.
-- 4. Crear una fila subscriptions por tenant.
-- 5. Poblar companies con id = perfiles_empresa.id para mantener compatibilidad con perfil_id.
