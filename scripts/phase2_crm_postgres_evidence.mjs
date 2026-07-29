import fs from "node:fs";
import { PGlite } from "/private/tmp/ge-phase0-pglite/node_modules/@electric-sql/pglite/dist/index.js";

const db = new PGlite();
await db.exec(fs.readFileSync("tests/fixtures/phase1_commercial_schema.sql", "utf8"));
const actor = "00000000-0000-0000-0000-000000000001";

await db.exec(`
  insert into commercial_prospects(
    business_name,legal_name,email,contact_name,estimated_rfc_count,stage,owner_user_id
  ) values
    ('Transportes A','Transportes A SA de CV','a@example.test','Ana',2,'qualified','${actor}'),
    ('Transportes B','','b@example.test','Beto',1,'new','${actor}');
  insert into commercial_prospect_contacts(prospect_id,name,is_primary) values(1,'Ana',true);
  insert into commercial_prospect_activities(
    prospect_id,activity_type,subject,occurred_at,actor_user_id
  ) values(1,'demo','Demostración','2026-07-28T12:00:00Z','${actor}');
`);

async function rejected(sql) {
  try { await db.exec(sql); return false; } catch { return true; }
}

const first = (await db.query(
  "select commercial_convert_prospect($1,$2,$3,$4,$5) result",
  [1, actor, "legal@example.test", "Ana", "Cotización aceptada"]
)).rows[0].result;
const second = (await db.query(
  "select commercial_convert_prospect($1,$2,$3,$4,$5) result",
  [1, actor, "legal@example.test", "Ana", "Reintento"]
)).rows[0].result;

const result = {
  firstConversionWasNew: first.already_converted === false,
  secondConversionWasIdempotent: second.already_converted === true,
  sameCustomer: first.customer.id === second.customer.id,
  customerCount: Number((await db.query("select count(*)::int n from commercial_customers")).rows[0].n),
  conversionAuditCount: Number((await db.query(
    "select count(*)::int n from commercial_audit_events where action='convert' and entity_id='1'"
  )).rows[0].n),
  prospectStage: (await db.query("select stage from commercial_prospects where id=1")).rows[0].stage,
  unqualifiedConversionRejected: await rejected(
    `select commercial_convert_prospect(2,'${actor}','x@example.test','Beto','Intento inválido')`
  ),
  duplicatePrimaryContactRejected: await rejected(
    "insert into commercial_prospect_contacts(prospect_id,name,is_primary) values(1,'Otra',true)"
  ),
  activityMutationRejected: await rejected(
    "update commercial_prospect_activities set subject='Alterada' where id=1"
  ),
  stageHistoryMutationRejected: await rejected(
    "delete from commercial_prospect_stage_events where prospect_id=1"
  ),
};

await db.exec("set role authenticated");
result.authenticatedVisibleProspects = Number(
  (await db.query("select count(*)::int n from commercial_prospects")).rows[0].n
);
result.authenticatedInsertRejected = await rejected(
  `insert into commercial_prospects(business_name,owner_user_id) values('Intruso','${actor}')`
);
result.authenticatedConversionRejected = await rejected(
  `select commercial_convert_prospect(1,'${actor}','x@example.test','X','Intruso')`
);
await db.exec("reset role");

console.log(JSON.stringify(result, null, 2));
await db.close();
