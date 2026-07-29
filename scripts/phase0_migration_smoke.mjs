import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const entry = process.env.PGLITE_ENTRY;
if (!entry) throw new Error("PGLITE_ENTRY es obligatorio.");
const { PGlite } = await import(pathToFileURL(entry).href);
const db = new PGlite();

await db.exec(`
  create role authenticated nologin;
  create schema auth;
  create table auth.users(id uuid primary key);
  create function auth.uid() returns uuid language sql stable
    as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  create table public.tenants(id uuid primary key);
  create table public.perfiles_empresa(
    id bigint primary key,
    tenant_id uuid references public.tenants(id),
    activo boolean not null default true
  );
`);

for (const name of [
  "tr_viajes", "tr_cfdi", "tr_facturas_servicio",
  "tr_facturas_servicio_cartas", "tr_vehiculos", "tr_choferes",
  "tr_clientes", "tr_rutas", "tr_viaje_documentos", "tr_operador_accesos",
]) {
  await db.exec(`create table public.${name}(id bigint primary key, perfil_id bigint);`);
}

const migrations = [
  "phase0_rfc_memberships_deferred_20260728.sql",
  "phase0_transport_scope_additive_deferred_20260728.sql",
  "phase0_transport_rls_enforcement_deferred_20260728.sql",
];
for (const migration of migrations) {
  const sql = fs.readFileSync(path.join(repoRoot, "migrations", migration), "utf8");
  await db.exec(sql);
}

const columns = await db.query(`
  select table_name, column_name
  from information_schema.columns
  where table_schema='public'
    and table_name in ('tr_viajes','tr_cfdi','tr_vehiculos')
    and column_name in ('tenant_id','subscription_id','deleted_at')
  order by table_name,column_name
`);
const membership = await db.query(`
  select relrowsecurity
  from pg_class
  where oid='public.rfc_access_memberships'::regclass
`);
if (columns.rows.length !== 7) {
  throw new Error(`Columnas aditivas inesperadas: ${JSON.stringify(columns.rows)}`);
}
if (membership.rows[0]?.relrowsecurity !== true) {
  throw new Error("rfc_access_memberships no tiene RLS habilitado");
}

process.stdout.write(JSON.stringify({
  ok: true,
  engine: "PGlite/PostgreSQL",
  migrations,
  checked_columns: columns.rows,
  membership_rls: true,
}, null, 2) + "\n");
await db.close();
