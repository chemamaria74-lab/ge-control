import fs from "node:fs";
import { PGlite } from "/private/tmp/ge-phase0-pglite/node_modules/@electric-sql/pglite/dist/index.js";
const db=new PGlite();
await db.exec("create role authenticated; create role service_role;");
await db.exec(fs.readFileSync("supabase/migrations/20260729131131_commercial_superadmin_phases_1_4.sql","utf8"));
const tables=Number((await db.query(`
  select count(*)::int n from information_schema.tables
  where table_schema='public' and table_name like 'commercial_%'
`)).rows[0].n);
const plans=Number((await db.query("select count(*)::int n from commercial_plans")).rows[0].n);
const legacy=Number((await db.query(`
  select count(*)::int n from commercial_subscriptions s
  join commercial_plan_versions pv on pv.id=s.plan_version_id
  join commercial_plans p on p.id=pv.plan_id where p.code='LEGACY_2800'
`)).rows[0].n);
console.log(JSON.stringify({tables,plans,legacyAssignments:legacy,migrationApplied:true},null,2));
await db.close();
