-- Beta de conciliación Gas LP: cierre diario, efectivo por depositar y banco.
-- No toca facturación; solo referencia empresa/perfil/tenant y datos de control interno.

create table if not exists public.gas_lp_conciliacion_cierres (
    id bigserial primary key,
    user_id uuid not null,
    tenant_id uuid,
    perfil_id bigint,
    facility_id bigint,
    fecha date not null,
    zona text default '',
    efectivo_reportado numeric(14,2) default 0,
    efectivo_depositado numeric(14,2) default 0,
    transferencia_reportada numeric(14,2) default 0,
    voucher_reportado numeric(14,2) default 0,
    cheque_reportado numeric(14,2) default 0,
    credito_reportado numeric(14,2) default 0,
    venta_publico_general numeric(14,2) default 0,
    descuento numeric(14,2) default 0,
    status text default 'pendiente_deposito',
    notas text default '',
    created_by_internal bigint,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_glp_conc_cierres_scope_fecha
    on public.gas_lp_conciliacion_cierres (user_id, perfil_id, fecha desc);

create table if not exists public.gas_lp_conciliacion_banco (
    id bigserial primary key,
    user_id uuid not null,
    tenant_id uuid,
    perfil_id bigint,
    fecha_banco date not null,
    banco text default '',
    cuenta text default '',
    descripcion text default '',
    referencia text default '',
    deposito numeric(14,2) default 0,
    retiro numeric(14,2) default 0,
    status text default 'sin_relacionar',
    notas text default '',
    created_by_internal bigint,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_glp_conc_banco_scope_fecha
    on public.gas_lp_conciliacion_banco (user_id, perfil_id, fecha_banco desc);

alter table public.gas_lp_conciliacion_cierres enable row level security;
alter table public.gas_lp_conciliacion_banco enable row level security;

revoke all on public.gas_lp_conciliacion_cierres from anon, authenticated;
revoke all on public.gas_lp_conciliacion_banco from anon, authenticated;
revoke all on sequence public.gas_lp_conciliacion_cierres_id_seq from anon, authenticated;
revoke all on sequence public.gas_lp_conciliacion_banco_id_seq from anon, authenticated;

drop policy if exists ge_glp_conc_cierres_backend_only_select on public.gas_lp_conciliacion_cierres;
create policy ge_glp_conc_cierres_backend_only_select
on public.gas_lp_conciliacion_cierres
for select to authenticated
using (false);

drop policy if exists ge_glp_conc_cierres_backend_only_insert on public.gas_lp_conciliacion_cierres;
create policy ge_glp_conc_cierres_backend_only_insert
on public.gas_lp_conciliacion_cierres
for insert to authenticated
with check (false);

drop policy if exists ge_glp_conc_cierres_backend_only_update on public.gas_lp_conciliacion_cierres;
create policy ge_glp_conc_cierres_backend_only_update
on public.gas_lp_conciliacion_cierres
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_glp_conc_cierres_backend_only_delete on public.gas_lp_conciliacion_cierres;
create policy ge_glp_conc_cierres_backend_only_delete
on public.gas_lp_conciliacion_cierres
for delete to authenticated
using (false);

drop policy if exists ge_glp_conc_banco_backend_only_select on public.gas_lp_conciliacion_banco;
create policy ge_glp_conc_banco_backend_only_select
on public.gas_lp_conciliacion_banco
for select to authenticated
using (false);

drop policy if exists ge_glp_conc_banco_backend_only_insert on public.gas_lp_conciliacion_banco;
create policy ge_glp_conc_banco_backend_only_insert
on public.gas_lp_conciliacion_banco
for insert to authenticated
with check (false);

drop policy if exists ge_glp_conc_banco_backend_only_update on public.gas_lp_conciliacion_banco;
create policy ge_glp_conc_banco_backend_only_update
on public.gas_lp_conciliacion_banco
for update to authenticated
using (false)
with check (false);

drop policy if exists ge_glp_conc_banco_backend_only_delete on public.gas_lp_conciliacion_banco;
create policy ge_glp_conc_banco_backend_only_delete
on public.gas_lp_conciliacion_banco
for delete to authenticated
using (false);
