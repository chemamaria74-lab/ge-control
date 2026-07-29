import fs from "node:fs";
import { PGlite } from "/private/tmp/ge-phase0-pglite/node_modules/@electric-sql/pglite/dist/index.js";

const db = new PGlite();
await db.exec(fs.readFileSync("tests/fixtures/phase1_commercial_schema.sql", "utf8"));
const actor = "00000000-0000-0000-0000-000000000001";
const userA = "10000000-0000-0000-0000-000000000001";
const userB = "20000000-0000-0000-0000-000000000002";

await db.exec(`
  insert into commercial_customers(name) values('Cliente A');
  insert into commercial_tax_entities(customer_id,rfc,legal_name,perfil_id)
    values(1,'AAA010101AAA','RFC A',101),(1,'AAB010101AAA','RFC B',102);
  insert into commercial_subscriptions(customer_id,tax_entity_id,plan_version_id,billing_period,status)
    values(1,1,1,'monthly','active'),(1,2,2,'monthly','active');
`);

async function rejected(sql, params=[]) {
  try { await db.query(sql, params); return false; } catch { return true; }
}
const invite = async (email,name) => (await db.query(
  "select commercial_invite_subscription_admin($1,$2,$3,$4,$5) result",
  [1,email,name,actor,"Autorizado"]
)).rows[0].result;

const first = await invite("admin-a@example.test","Admin A");
const result = {
  firstInviteOccupied: first.occupied === 1,
  secondInviteAtBaseLimitRejected: await rejected(
    "select commercial_invite_subscription_admin($1,$2,$3,$4,$5)",
    [1,"admin-b@example.test","Admin B",actor,"Segundo"]
  ),
};

await db.query(
  "select commercial_change_admin_membership_status($1,$2,$3,$4,$5,$6)",
  [1,"active",userA,actor,"Invitación aceptada",false]
);
result.lastActiveSuspendRejected = await rejected(
  "select commercial_change_admin_membership_status($1,$2,$3,$4,$5,$6)",
  [1,"suspended",null,actor,"Sin sustituto",false]
);

await db.exec(`
  insert into subscription_limit_overrides(
    subscription_id,override_code,integer_value,starts_at,ends_at,reason,
    approved_by,approved_at,status
  ) values(
    1,'administrator_limit',2,now()-interval '1 minute',now()+interval '1 day',
    'Cupo temporal','${actor}',now(),'active'
  );
`);
const second = await invite("admin-b@example.test","Admin B");
result.overrideAllowedSecondInvite = second.occupied === 2 && second.capacity === 2;
await db.query(
  "select commercial_change_admin_membership_status($1,$2,$3,$4,$5,$6)",
  [2,"active",userB,actor,"Invitación aceptada",false]
);
result.suspendWithReplacementSucceeded = !(await rejected(
  "select commercial_change_admin_membership_status($1,$2,$3,$4,$5,$6)",
  [1,"suspended",null,actor,"Existe sustituto",false]
));

await db.exec(`
  insert into subscription_addons(
    subscription_id,addon_code,billing_mode,agreed_subtotal,tax,total,
    starts_at,ends_at,reason,status,approved_by
  ) values
    (1,'OPERATOR_PORTAL','trial',0,0,0,now()-interval '2 months',
      now()-interval '1 second','Prueba vencida','active','${actor}'),
    (2,'OPERATOR_PORTAL','trial',0,0,0,now()-interval '1 month',
      now()+interval '1 month','Prueba vigente','active','${actor}');
`);
result.expiredPortalDenied = !(await db.query(
  "select commercial_operator_portal_effective(1,now()) value"
)).rows[0].value;
result.currentPortalAllowed = (await db.query(
  "select commercial_operator_portal_effective(2,now()) value"
)).rows[0].value;

await db.exec("set role authenticated");
result.authenticatedMembershipRows = Number((await db.query(
  "select count(*)::int n from subscription_administrator_memberships"
)).rows[0].n);
result.authenticatedInviteRpcRejected = await rejected(
  "select commercial_invite_subscription_admin($1,$2,$3,$4,$5)",
  [2,"intruso@example.test","Intruso",actor,"Intruso"]
);
await db.exec("reset role");

result.legacyAssignments = Number((await db.query(`
  select count(*)::int n from commercial_subscriptions s
  join commercial_plan_versions pv on pv.id=s.plan_version_id
  join commercial_plans p on p.id=pv.plan_id where p.code='LEGACY_2800'
`)).rows[0].n);
console.log(JSON.stringify(result,null,2));
await db.close();
