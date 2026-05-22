-- GE Control / Z Control - Supabase hygiene audit
-- Non destructive. Run in Supabase SQL editor against STAGING only.
-- It creates only TEMP tables for the current session.

-- 1) Exact public table row counts.
create temp table if not exists audit_table_counts (
  schema_name text,
  table_name text,
  row_count bigint
) on commit drop;

truncate audit_table_counts;

do $$
declare
  r record;
begin
  for r in
    select schemaname, tablename
    from pg_tables
    where schemaname = 'public'
    order by tablename
  loop
    execute format(
      'insert into audit_table_counts(schema_name, table_name, row_count) select %L, %L, count(*) from %I.%I',
      r.schemaname, r.tablename, r.schemaname, r.tablename
    );
  end loop;
end $$;

select
  c.schema_name,
  c.table_name,
  c.row_count,
  pg_size_pretty(pg_total_relation_size(format('%I.%I', c.schema_name, c.table_name)::regclass)) as total_size,
  s.n_live_tup as planner_live_rows,
  s.seq_scan,
  s.idx_scan,
  s.last_vacuum,
  s.last_autovacuum
from audit_table_counts c
left join pg_stat_user_tables s
  on s.schemaname = c.schema_name
 and s.relname = c.table_name
order by c.row_count asc, pg_total_relation_size(format('%I.%I', c.schema_name, c.table_name)::regclass) desc;

-- 2) RLS / policy inventory.
select
  n.nspname as schema_name,
  cls.relname as table_name,
  cls.relrowsecurity as rls_enabled,
  cls.relforcerowsecurity as rls_forced,
  count(pol.polname) as policy_count,
  string_agg(pol.polname::text || ':' || pol.polcmd::text, ', ' order by pol.polname) as policies
from pg_class cls
join pg_namespace n on n.oid = cls.relnamespace
left join pg_policy pol on pol.polrelid = cls.oid
where cls.relkind = 'r'
  and n.nspname in ('public', 'storage')
group by n.nspname, cls.relname, cls.relrowsecurity, cls.relforcerowsecurity
order by n.nspname, cls.relname;

-- 3) Potentially risky policies.
select
  schemaname,
  tablename,
  policyname,
  cmd,
  roles,
  qual,
  with_check
from pg_policies
where schemaname in ('public', 'storage')
  and (
    coalesce(qual, '') ilike '%true%'
    or coalesce(with_check, '') ilike '%true%'
    or roles::text ilike '%public%'
    or roles::text ilike '%anon%'
  )
order by schemaname, tablename, policyname;

-- 4) Tables with scope columns, useful to standardize tenant/company/perfil/user.
select
  table_schema,
  table_name,
  string_agg(column_name, ', ' order by column_name) filter (
    where column_name in ('tenant_id', 'company_id', 'perfil_id', 'user_id', 'owner_user_id', 'created_by')
  ) as scope_columns,
  count(*) filter (
    where column_name in ('tenant_id', 'company_id', 'perfil_id', 'user_id', 'owner_user_id', 'created_by')
  ) as scope_column_count
from information_schema.columns
where table_schema = 'public'
group by table_schema, table_name
order by scope_column_count asc, table_name;

-- 5) Duplicate-ish / legacy-ish naming candidates.
select
  table_name,
  row_count,
  case
    when table_name ilike '%legacy%' then 'legacy-name'
    when table_name ilike '%mock%' then 'mock-name'
    when table_name ilike '%test%' then 'test-name'
    when table_name ilike '%old%' then 'old-name'
    when table_name ilike '%tmp%' then 'tmp-name'
    when row_count = 0 then 'empty'
    else ''
  end as reason
from audit_table_counts
where table_name ilike '%legacy%'
   or table_name ilike '%mock%'
   or table_name ilike '%test%'
   or table_name ilike '%old%'
   or table_name ilike '%tmp%'
   or row_count = 0
order by reason, table_name;

-- 6) Column inventory and suspicious defaults.
select
  table_schema,
  table_name,
  column_name,
  data_type,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and (
    column_name ilike '%legacy%'
    or column_name ilike '%mock%'
    or column_name ilike '%test%'
    or column_name ilike '%tmp%'
    or column_name in ('data', 'metadata', 'raw', 'raw_json')
    or column_default ilike '%XAXX010101000%'
    or column_default ilike '%example%'
  )
order by table_name, ordinal_position;

-- 7) Index inventory and duplicated index definitions.
with idx as (
  select
    schemaname,
    tablename,
    indexname,
    indexdef,
    regexp_replace(indexdef, '^CREATE (UNIQUE )?INDEX [^ ]+ ', 'CREATE INDEX ', 'i') as normalized_def
  from pg_indexes
  where schemaname = 'public'
)
select
  schemaname,
  tablename,
  normalized_def,
  count(*) as duplicate_count,
  string_agg(indexname, ', ' order by indexname) as indexes
from idx
group by schemaname, tablename, normalized_def
having count(*) > 1
order by duplicate_count desc, tablename;

-- 8) Missing FK indexes.
select
  conrelid::regclass as table_name,
  conname as fk_name,
  pg_get_constraintdef(oid) as fk_def
from pg_constraint c
where contype = 'f'
  and connamespace = 'public'::regnamespace
  and not exists (
    select 1
    from pg_index i
    where i.indrelid = c.conrelid
      and i.indkey::int2[] @> c.conkey
  )
order by conrelid::regclass::text, conname;

-- 9) Storage buckets and object counts.
select
  b.id,
  b.name,
  b.public,
  b.file_size_limit,
  b.allowed_mime_types,
  count(o.id) as object_count,
  pg_size_pretty(
    coalesce(
      sum(
        case
          when (o.metadata->>'size') ~ '^[0-9]+$' then (o.metadata->>'size')::bigint
          else 0
        end
      ),
      0
    )
  ) as estimated_object_size
from storage.buckets b
left join storage.objects o on o.bucket_id = b.id
group by b.id, b.name, b.public, b.file_size_limit, b.allowed_mime_types
order by object_count asc, b.name;

-- 10) Orphan-ish storage objects by known fiscal/document prefixes.
select
  bucket_id,
  split_part(name, '/', 1) as top_prefix,
  count(*) as object_count,
  max(created_at) as last_created_at
from storage.objects
group by bucket_id, split_part(name, '/', 1)
order by bucket_id, object_count desc;

-- 11) High-growth tables: check indexes and row counts.
select
  c.table_name,
  c.row_count,
  pg_size_pretty(pg_total_relation_size(format('%I.%I', c.schema_name, c.table_name)::regclass)) as total_size,
  coalesce(string_agg(i.indexname, ', ' order by i.indexname), 'NO INDEXES') as indexes
from audit_table_counts c
left join pg_indexes i
  on i.schemaname = c.schema_name
 and i.tablename = c.table_name
where c.table_name in (
  'cfdi_sat_inbox',
  'detected_loads',
  'fiscal_document_events',
  'pac_requests',
  'pac_responses',
  'xml_versions',
  'invoice_cancellations',
  'tr_viaje_eventos',
  'internal_user_sessions',
  'gaso_market_price_snapshots',
  'gaso_ingestion_runs'
)
group by c.schema_name, c.table_name, c.row_count
order by c.row_count desc;
