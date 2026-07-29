import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const fixturePath = path.join(repoRoot, "tests", "fixtures", "phase0_tenant_isolation.json");
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const entry = process.env.PGLITE_ENTRY;
if (!entry) {
  throw new Error("PGLITE_ENTRY es obligatorio y debe apuntar a @electric-sql/pglite/dist/index.js");
}
const { PGlite } = await import(pathToFileURL(entry).href);
const db = new PGlite();

await db.exec(`
  create role authenticated nologin;
  create schema auth;
  create function auth.uid() returns uuid
  language sql stable
  as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

  create table tenants (
    id uuid primary key,
    name text not null
  );
  create table perfiles_empresa (
    id bigint primary key,
    tenant_id uuid not null references tenants(id),
    activo boolean not null default true,
    unique (tenant_id, id)
  );
  create table rfc_access_memberships (
    id bigint generated always as identity primary key,
    tenant_id uuid not null,
    perfil_id bigint not null,
    user_id uuid not null,
    section text not null,
    role text not null,
    status text not null,
    foreign key (tenant_id, perfil_id) references perfiles_empresa(tenant_id, id),
    unique (user_id, section, perfil_id)
  );
  create table tr_viajes (
    id bigint primary key,
    tenant_id uuid not null,
    perfil_id bigint not null,
    description text not null,
    foreign key (tenant_id, perfil_id) references perfiles_empresa(tenant_id, id)
  );

  alter table tr_viajes enable row level security;
  create policy tr_viajes_rfc_membership
    on tr_viajes for all to authenticated
    using (
      exists (
        select 1 from rfc_access_memberships membership
        where membership.user_id = (select auth.uid())
          and membership.section = 'transporte'
          and membership.status = 'active'
          and membership.tenant_id = tr_viajes.tenant_id
          and membership.perfil_id = tr_viajes.perfil_id
      )
    )
    with check (
      exists (
        select 1 from rfc_access_memberships membership
        where membership.user_id = (select auth.uid())
          and membership.section = 'transporte'
          and membership.status = 'active'
          and membership.tenant_id = tr_viajes.tenant_id
          and membership.perfil_id = tr_viajes.perfil_id
      )
    );
  grant usage on schema public, auth to authenticated;
  grant select on rfc_access_memberships to authenticated;
  grant select, insert, update, delete on tr_viajes to authenticated;
`);

const ta = fixture.tenants.a;
const tb = fixture.tenants.b;
const pa = fixture.profiles.rfc_a;
const pbSame = fixture.profiles.rfc_b_same_tenant;
const pbOther = fixture.profiles.rfc_b_other_tenant;
const ua = fixture.users.admin_a;
const ub = fixture.users.admin_b;
const um = fixture.users.multi_rfc;

await db.query(
  `insert into tenants values ($1,'Tenant A'),($2,'Tenant B')`,
  [ta, tb],
);
await db.query(
  `insert into perfiles_empresa(id,tenant_id) values ($1,$2),($3,$2),($4,$5)`,
  [pa, ta, pbSame, pbOther, tb],
);
await db.query(
  `insert into rfc_access_memberships(tenant_id,perfil_id,user_id,section,role,status)
   values
   ($1,$2,$3,'transporte','admin','active'),
   ($4,$5,$6,'transporte','admin','active'),
   ($1,$2,$7,'transporte','admin','active'),
   ($1,$8,$7,'transporte','admin','active')`,
  [ta, pa, ua, tb, pbOther, ub, um, pbSame],
);
await db.query(
  `insert into tr_viajes values
   (1,$1,$2,'A/RFC-A'),(2,$1,$3,'A/RFC-B'),(3,$4,$5,'B/RFC-B')`,
  [ta, pa, pbSame, tb, pbOther],
);

async function asUser(userId, operation) {
  await db.exec("set role authenticated");
  await db.query("select set_config('request.jwt.claim.sub', $1, false)", [userId]);
  try {
    return await operation();
  } finally {
    await db.exec("reset role");
    await db.query("select set_config('request.jwt.claim.sub', '', false)");
  }
}

async function visibleTrips(userId) {
  const result = await asUser(userId, () => db.query("select id from tr_viajes order by id"));
  return result.rows.map((row) => Number(row.id));
}

async function isBlocked(userId, sql, params) {
  try {
    await asUser(userId, () => db.query(sql, params));
    return false;
  } catch {
    return true;
  }
}

const evidence = {
  engine: "PGlite/PostgreSQL",
  admin_a_visible_trip_ids: await visibleTrips(ua),
  admin_b_visible_trip_ids: await visibleTrips(ub),
  multi_rfc_visible_trip_ids: await visibleTrips(um),
  admin_a_cannot_insert_rfc_b_same_tenant: await isBlocked(
    ua,
    "insert into tr_viajes values (4,$1,$2,'forged')",
    [ta, pbSame],
  ),
  admin_a_cannot_update_tenant_b: await isBlocked(
    ua,
    "update tr_viajes set description='forged' where id=3 returning id",
    [],
  ),
  admin_a_cannot_delete_tenant_b: false,
};

const deleteResult = await asUser(ua, () => db.query("delete from tr_viajes where id=3 returning id"));
evidence.admin_a_cannot_delete_tenant_b = deleteResult.rows.length === 0;

// UPDATE on an invisible row is correctly a zero-row result, not an error.
const updateResult = await asUser(ua, () => db.query(
  "update tr_viajes set description='forged' where id=3 returning id",
));
evidence.admin_a_cannot_update_tenant_b = updateResult.rows.length === 0;

for (const [key, expected] of Object.entries(fixture.expected)) {
  if (JSON.stringify(evidence[key]) !== JSON.stringify(expected)) {
    throw new Error(`Evidencia RLS incorrecta para ${key}: ${JSON.stringify(evidence[key])}`);
  }
}

process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
await db.close();
