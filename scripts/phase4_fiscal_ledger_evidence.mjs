import fs from "node:fs";
import { PGlite } from "/private/tmp/ge-phase0-pglite/node_modules/@electric-sql/pglite/dist/index.js";
const db=new PGlite();
await db.exec(fs.readFileSync("tests/fixtures/phase1_commercial_schema.sql","utf8"));
const actor="00000000-0000-0000-0000-000000000001";
await db.exec(`
  update commercial_plan_versions set monthly_fiscal_trip_limit=2 where id=1;
  insert into commercial_customers(name) values('Cliente Fiscal');
  insert into commercial_tax_entities(customer_id,rfc,legal_name) values(1,'AAA010101AAA','RFC Fiscal');
  insert into commercial_subscriptions(customer_id,tax_entity_id,plan_version_id,billing_period,status)
    values(1,1,1,'monthly','active');
`);
async function record(uuid,type,cfdi,trip){return (await db.query(
  "select commercial_record_fiscal_trip($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) result",
  [1,1,cfdi,trip,uuid,type,"2026-07-29T12:00:00Z",actor,"Evento fiscal",{}]
)).rows[0].result}
async function rejected(fn){try{await fn();return false}catch{return true}}
const first=await record("UUID-CP-1","carta_porte_stamped",10,100);
const retry=await record("UUID-CP-1","carta_porte_stamped",10,100);
const replacement=await record("UUID-CP-2","replacement_stamped",11,100);
const result={
  firstConsumed:first.capacity.consumed===1,
  retryIdempotent:retry.idempotent===true,
  replacementConsumed:replacement.capacity.consumed===2,
  twoEventsOnly:Number((await db.query("select count(*)::int n from commercial_fiscal_trip_ledger")).rows[0].n)===2,
  thirdStampBlocked:await rejected(()=>record("UUID-CP-3","carta_porte_stamped",12,101)),
  incomeCfdiRejected:await rejected(()=>record("UUID-I-1","income_cfdi",13,100)),
};
await db.exec(`
  insert into commercial_fiscal_trip_ledger(
    subscription_id,tax_entity_id,event_type,quantity,idempotency_key,occurred_at,
    period_month,reason,actor_user_id
  ) values(1,1,'technical_compensation',-1,'adjustment:1','2026-07-29T13:00:00Z',
    '2026-07-01','Error técnico interno comprobado','${actor}');
`);
result.compensationPreservesOriginal=Number((await db.query(
  "select count(*)::int n from commercial_fiscal_trip_ledger"
)).rows[0].n)===3;
result.adjustedConsumed=Number((await db.query(
  "select sum(quantity)::int n from commercial_fiscal_trip_ledger"
)).rows[0].n)===1;
result.ledgerMutationRejected=await rejected(()=>db.exec(
  "delete from commercial_fiscal_trip_ledger where id=1"
));
await db.exec("set role authenticated");
result.authenticatedLedgerRows=Number((await db.query(
  "select count(*)::int n from commercial_fiscal_trip_ledger"
)).rows[0].n);
await db.exec("reset role");
console.log(JSON.stringify(result,null,2));await db.close();
