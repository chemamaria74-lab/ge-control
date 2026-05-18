-- GE CONTROL - Panel interno Superadmin SaaS
-- Idempotente y no destructivo.

create table if not exists public.admin_saas_audit (
  id bigserial primary key,
  actor_user_id uuid,
  action text not null,
  target_type text not null default '',
  target_id text not null default '',
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_admin_saas_audit_created
  on public.admin_saas_audit(created_at desc);

create index if not exists idx_admin_saas_audit_actor
  on public.admin_saas_audit(actor_user_id, created_at desc);

alter table public.admin_saas_audit enable row level security;

drop policy if exists admin_saas_audit_no_client_access on public.admin_saas_audit;
create policy admin_saas_audit_no_client_access
  on public.admin_saas_audit
  for all to authenticated
  using (false)
  with check (false);

-- El panel usa backend con service_role + allowlist SUPERADMIN_USER_IDS/SUPERADMIN_EMAILS.
-- No exponer esta tabla directo al cliente.

