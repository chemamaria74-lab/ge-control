-- GE CONTROL - Usuarios internos por empresa/perfil
-- Operadores sin Supabase Auth y asistentes internos por módulo.

alter table public.user_sections
  drop constraint if exists user_sections_role_check;

alter table public.user_sections
  add constraint user_sections_role_check
  check (role in ('admin', 'user', 'operador', 'asistente_facturacion', 'asistente_operativo', 'planta', 'solo_lectura'));

create table if not exists public.internal_users (
  id bigserial primary key,
  tenant_id uuid,
  owner_user_id uuid not null,
  perfil_id bigint not null,
  section text not null,
  role text not null,
  display_name text not null,
  code text not null,
  pin_hash text not null,
  status text not null default 'active',
  chofer_id bigint,
  permissions jsonb not null default '{}'::jsonb,
  failed_attempts integer not null default 0,
  locked_until timestamptz,
  last_access_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (section in ('transporte', 'gas_lp', 'gasolineras')),
  check (role in ('admin', 'operador', 'asistente_facturacion', 'asistente_operativo', 'planta', 'solo_lectura')),
  check (status in ('active', 'inactive', 'locked')),
  unique (tenant_id, code)
);

create table if not exists public.internal_user_sessions (
  id bigserial primary key,
  internal_user_id bigint not null references public.internal_users(id) on delete cascade,
  tenant_id uuid,
  perfil_id bigint not null,
  section text not null,
  role text not null,
  token_hash text not null unique,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_internal_users_scope
  on public.internal_users(tenant_id, owner_user_id, perfil_id, section, role, status);

create index if not exists idx_internal_users_code
  on public.internal_users(code, section, status);

create index if not exists idx_internal_sessions_token
  on public.internal_user_sessions(token_hash, expires_at);

alter table public.internal_users enable row level security;
alter table public.internal_user_sessions enable row level security;

drop policy if exists internal_users_owner_policy on public.internal_users;
create policy internal_users_owner_policy
  on public.internal_users for all to authenticated
  using (owner_user_id = auth.uid())
  with check (owner_user_id = auth.uid());

drop policy if exists internal_sessions_owner_policy on public.internal_user_sessions;
create policy internal_sessions_owner_policy
  on public.internal_user_sessions for select to authenticated
  using (
    exists (
      select 1 from public.internal_users iu
      where iu.id = internal_user_sessions.internal_user_id
      and iu.owner_user_id = auth.uid()
    )
  );
