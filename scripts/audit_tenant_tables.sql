-- Sprint 0: auditoría read-only del scope tenant/company y RLS efectivo.
-- Ejecutar con un rol que pueda leer pg_catalog y las tablas public.
-- No modifica datos ni políticas; sólo crea tablas temporales de sesión.

begin transaction read only;

create temporary table ge_tenant_scope_audit (
  schema_name text,
  table_name text,
  rls_enabled boolean,
  has_tenant_id boolean,
  tenant_id_nullable boolean,
  company_scope_columns text[],
  foreign_keys jsonb,
  tenant_indexes text[],
  composite_scope_indexes text[],
  policies_using jsonb,
  policies_with_check jsonb,
  policy_count integer,
  tenant_null_rows bigint,
  company_scope_null_rows bigint,
  audit_error text
) on commit drop;

do $audit$
declare
  relation record;
  tenant_nulls bigint;
  company_nulls bigint;
  company_column text;
  error_text text;
begin
  for relation in
    select n.nspname schema_name, c.relname table_name, c.relrowsecurity rls_enabled,
           exists (
             select 1 from pg_attribute a
             where a.attrelid = c.oid and a.attname = 'tenant_id' and not a.attisdropped
           ) has_tenant_id,
           coalesce((
             select not a.attnotnull from pg_attribute a
             where a.attrelid = c.oid and a.attname = 'tenant_id' and not a.attisdropped
           ), false) tenant_id_nullable,
           array(
             select a.attname from pg_attribute a
             where a.attrelid = c.oid and a.attname in ('company_id', 'perfil_id') and not a.attisdropped
             order by a.attname
           ) company_scope_columns,
           c.oid
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind in ('r', 'p')
      and (
        c.relname like 'tr\_%' escape '\'
        or c.relname like 'gas\_lp\_%' escape '\'
        or c.relname in (
          'providers', 'records', 'reports', 'user_facilities', 'zc_settings',
          'internal_users', 'internal_user_sessions', 'fiscal_document_events',
          'fiscal_audit_events', 'pac_requests', 'sat_credentials', 'sat_sync_jobs',
          'cfdi_sat_inbox', 'detected_loads', 'companies', 'user_sections'
        )
      )
    order by c.relname
  loop
    tenant_nulls := null;
    company_nulls := null;
    error_text := null;
    begin
      if relation.has_tenant_id then
        execute format('select count(*) from %I.%I where tenant_id is null', relation.schema_name, relation.table_name)
          into tenant_nulls;
      end if;
      if cardinality(relation.company_scope_columns) > 0 then
        company_column := relation.company_scope_columns[1];
        execute format('select count(*) from %I.%I where %I is null', relation.schema_name, relation.table_name, company_column)
          into company_nulls;
      end if;
    exception when others then
      error_text := sqlstate || ': ' || sqlerrm;
    end;

    insert into ge_tenant_scope_audit
    select
      relation.schema_name,
      relation.table_name,
      relation.rls_enabled,
      relation.has_tenant_id,
      relation.tenant_id_nullable,
      relation.company_scope_columns,
      coalesce((
        select jsonb_agg(jsonb_build_object(
          'name', con.conname,
          'definition', pg_get_constraintdef(con.oid, true)
        ) order by con.conname)
        from pg_constraint con where con.conrelid = relation.oid and con.contype = 'f'
      ), '[]'::jsonb),
      array(
        select indexdef from pg_indexes
        where schemaname = relation.schema_name and tablename = relation.table_name
          and indexdef ilike '%tenant_id%'
        order by indexname
      ),
      array(
        select indexdef from pg_indexes
        where schemaname = relation.schema_name and tablename = relation.table_name
          and (
            (indexdef ilike '%tenant_id%' and (indexdef ilike '%company_id%' or indexdef ilike '%perfil_id%'))
            or (indexdef ilike '%user_id%' and indexdef ilike '%perfil_id%')
          )
        order by indexname
      ),
      coalesce((
        select jsonb_agg(jsonb_build_object('policy', pol.polname, 'command', pol.polcmd, 'using', pg_get_expr(pol.polqual, pol.polrelid)) order by pol.polname)
        from pg_policy pol where pol.polrelid = relation.oid and pol.polqual is not null
      ), '[]'::jsonb),
      coalesce((
        select jsonb_agg(jsonb_build_object('policy', pol.polname, 'command', pol.polcmd, 'with_check', pg_get_expr(pol.polwithcheck, pol.polrelid)) order by pol.polname)
        from pg_policy pol where pol.polrelid = relation.oid and pol.polwithcheck is not null
      ), '[]'::jsonb),
      (select count(*) from pg_policy pol where pol.polrelid = relation.oid),
      tenant_nulls,
      company_nulls,
      error_text;
  end loop;
end
$audit$;

select * from ge_tenant_scope_audit order by table_name;

-- Resumen que hace fallar visualmente los controles más importantes.
select
  count(*) filter (where not rls_enabled) as tables_without_rls,
  count(*) filter (where policy_count = 0) as tables_without_policies,
  count(*) filter (where has_tenant_id and tenant_id_nullable) as nullable_tenant_columns,
  coalesce(sum(tenant_null_rows), 0) as rows_with_null_tenant,
  coalesce(sum(company_scope_null_rows), 0) as rows_with_null_company_scope,
  count(*) filter (where has_tenant_id and cardinality(tenant_indexes) = 0) as tables_without_tenant_index,
  count(*) filter (where policy_count > 0 and policies_with_check = '[]'::jsonb) as tables_without_with_check
from ge_tenant_scope_audit;

rollback;
