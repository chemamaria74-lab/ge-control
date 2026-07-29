import fs from "node:fs";
import { PGlite } from "/private/tmp/ge-phase0-pglite/node_modules/@electric-sql/pglite/dist/index.js";

const schema = fs.readFileSync("tests/fixtures/phase1_commercial_schema.sql", "utf8");
const db = new PGlite();
await db.exec(schema);

const result = {};
result.planDrafts = (await db.query("select code,status,commercializable,legacy,grandfathered from commercial_plans order by id")).rows;
result.legacyAssignments = Number((await db.query(`
  select count(*)::int n from commercial_subscriptions s
  join commercial_plan_versions pv on pv.id=s.plan_version_id
  join commercial_plans p on p.id=pv.plan_id where p.code='LEGACY_2800'
`)).rows[0].n);

await db.exec(`
  insert into commercial_customers(name,contractual_email) values
    ('Tenant A','a@example.test'),('Tenant B','b@example.test');
  insert into commercial_tax_entities(customer_id,rfc,legal_name) values
    (1,'AAA010101AAA','RFC A'),(1,'AAB010101AAA','RFC B'),(2,'BBB010101BBB','RFC ajeno');
  insert into commercial_subscriptions(customer_id,tax_entity_id,plan_version_id,billing_period,status)
    values (1,1,2,'monthly','active'),(1,2,2,'monthly','active');
`);
result.independentRfcSubscriptions = Number((await db.query(
  "select count(*)::int n from commercial_subscriptions where customer_id=1 and status='active'"
)).rows[0].n);

async function rejected(sql) {
  try { await db.exec(sql); return false; } catch { return true; }
}
result.duplicateOperationalRejected = await rejected(
  "insert into commercial_subscriptions(customer_id,tax_entity_id,plan_version_id,billing_period,status) values(1,1,2,'monthly','suspended')"
);
result.crossCustomerRejected = await rejected(
  "insert into commercial_subscriptions(customer_id,tax_entity_id,plan_version_id,billing_period,status) values(1,3,2,'monthly','active')"
);
result.pinLimitRejected = await rejected(
  "insert into commercial_plan_versions(plan_id,version_number,pin_operator_limit,status) values(1,99,1,'draft')"
);
result.longTrialRejected = await rejected(`
  insert into subscription_addons(subscription_id,addon_code,billing_mode,starts_at,ends_at,reason,approved_by,tax,total)
  values(1,'OPERATOR_PORTAL','trial','2026-01-01','2026-04-02','prueba',
    '00000000-0000-0000-0000-000000000001',0,0)
`);
await db.exec("update commercial_plan_versions set status='published' where id=1");
result.publishedVersionImmutable = await rejected(
  "update commercial_plan_versions set vehicle_limit=999 where id=1"
);

await db.exec("set role authenticated");
result.authenticatedVisibleCustomers = Number((await db.query("select count(*)::int n from commercial_customers")).rows[0].n);
result.authenticatedInsertRejected = await rejected(
  "insert into commercial_customers(name) values('Intruso')"
);
await db.exec("reset role");

console.log(JSON.stringify(result, null, 2));
await db.close();
