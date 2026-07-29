-- Esquema de prueba Fase 1. NO ES MIGRACION Y NO DEBE APLICARSE EN SUPABASE.

create role authenticated;
create role service_role;

create table commercial_customers (
  id bigint generated always as identity primary key,
  tenant_id uuid,
  name text not null,
  contractual_email text not null default '',
  authorized_contact text not null default '',
  phone text not null default '',
  address text not null default '',
  notes text not null default '',
  status text not null default 'draft' check(status in ('draft','onboarding','active','suspended','canceled','archived')),
  legacy boolean not null default false,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_prospects (
  id bigint generated always as identity primary key,
  business_name text not null,
  legal_name text not null default '',
  source text not null default 'direct',
  email text not null default '',
  phone text not null default '',
  contact_name text not null default '',
  estimated_rfc_count integer not null default 1 check(estimated_rfc_count between 1 and 100),
  expected_close_on date,
  notes text not null default '',
  stage text not null default 'new' check(stage in ('new','contacted','qualified','proposal','negotiation','won','lost','disqualified')),
  lost_reason text not null default '',
  owner_user_id uuid not null,
  converted_customer_id bigint unique references commercial_customers(id),
  converted_at timestamptz,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_prospect_contacts (
  id bigint generated always as identity primary key,
  prospect_id bigint not null references commercial_prospects(id),
  name text not null,
  role text not null default '',
  email text not null default '',
  phone text not null default '',
  is_primary boolean not null default false,
  notes text not null default '',
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index commercial_prospect_one_primary_contact
  on commercial_prospect_contacts(prospect_id) where is_primary;

create table commercial_prospect_activities (
  id bigint generated always as identity primary key,
  prospect_id bigint not null references commercial_prospects(id),
  activity_type text not null check(activity_type in ('note','call','meeting','demo','email','follow_up')),
  subject text not null,
  details text not null default '',
  occurred_at timestamptz not null,
  actor_user_id uuid not null,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_prospect_tasks (
  id bigint generated always as identity primary key,
  prospect_id bigint not null references commercial_prospects(id),
  title text not null,
  due_at timestamptz not null,
  assigned_user_id uuid not null,
  priority text not null default 'normal' check(priority in ('low','normal','high','urgent')),
  status text not null default 'pending' check(status in ('pending','completed','canceled')),
  completed_at timestamptz,
  notes text not null default '',
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check((status='completed' and completed_at is not null) or status<>'completed')
);

create table commercial_prospect_stage_events (
  id bigint generated always as identity primary key,
  prospect_id bigint not null references commercial_prospects(id),
  from_stage text,
  to_stage text not null,
  reason text not null,
  actor_user_id uuid not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_tax_entities (
  id bigint generated always as identity primary key,
  customer_id bigint not null references commercial_customers(id),
  rfc text not null check(char_length(rfc) in (12,13)),
  legal_name text not null,
  fiscal_regime text not null default '',
  fiscal_postal_code text not null default '',
  fiscal_address text not null default '',
  perfil_id bigint,
  company_id bigint,
  status text not null default 'draft' check(status in ('draft','validated','active','inactive')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(customer_id,rfc)
);
alter table commercial_tax_entities add constraint commercial_tax_entities_customer_id_id_key unique(customer_id,id);

create table commercial_plans (
  id bigint generated always as identity primary key,
  code text not null unique,
  name text not null,
  commercializable boolean not null default true,
  legacy boolean not null default false,
  grandfathered boolean not null default false,
  description text not null default '',
  status text not null default 'draft' check(status in ('draft','active','retired')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_plan_versions (
  id bigint generated always as identity primary key,
  plan_id bigint not null references commercial_plans(id),
  version_number integer not null check(version_number>0),
  vehicle_limit integer check(vehicle_limit is null or vehicle_limit>=0),
  monthly_fiscal_trip_limit integer check(monthly_fiscal_trip_limit is null or monthly_fiscal_trip_limit>=0),
  administrator_limit integer check(administrator_limit is null or administrator_limit>=1),
  pin_operator_limit integer,
  effective_from date,
  notes text not null default '',
  status text not null default 'draft' check(status in ('draft','published','retired')),
  limits_snapshot jsonb not null default '{}'::jsonb,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(plan_id,version_number),
  check(pin_operator_limit is null)
);

create table commercial_price_versions (
  id bigint generated always as identity primary key,
  plan_version_id bigint not null references commercial_plan_versions(id),
  billing_period text not null check(billing_period in ('monthly','annual')),
  subtotal numeric(14,2) not null check(subtotal>=0),
  tax_rate numeric(7,6) not null default .16 check(tax_rate between 0 and 1),
  tax numeric(14,2) not null,
  total numeric(14,2) not null,
  currency text not null default 'MXN' check(currency='MXN'),
  effective_from date,
  notes text not null default '',
  status text not null default 'draft' check(status in ('draft','published','retired')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_subscriptions (
  id bigint generated always as identity primary key,
  customer_id bigint not null references commercial_customers(id),
  tax_entity_id bigint not null,
  plan_version_id bigint not null references commercial_plan_versions(id),
  price_version_id bigint references commercial_price_versions(id),
  billing_period text not null check(billing_period in ('monthly','annual')),
  currency text not null default 'MXN' check(currency='MXN'),
  starts_on date, renews_on date,
  status text not null default 'draft' check(status in ('draft','pending_activation','trialing','active','suspended','canceled','expired')),
  legacy boolean not null default false,
  grandfathered boolean not null default false,
  notes text not null default '',
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  foreign key(customer_id,tax_entity_id) references commercial_tax_entities(customer_id,id)
);
create unique index commercial_subscription_one_operational_per_rfc
  on commercial_subscriptions(tax_entity_id)
  where status in ('pending_activation','trialing','active','suspended');

create table subscription_term_versions (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  version_number integer not null,
  vehicle_limit integer,
  monthly_fiscal_trip_limit integer,
  administrator_limit integer,
  pin_operator_limit integer,
  subtotal numeric(14,2) not null,
  tax_rate numeric(7,6) not null,
  gross_subtotal numeric(14,2) not null,
  discount numeric(14,2) not null,
  net_subtotal numeric(14,2) not null,
  tax numeric(14,2) not null,
  total numeric(14,2) not null,
  billing_period text not null,
  effective_from date not null,
  effective_until date,
  payment_terms text not null,
  reason text not null default '',
  status text not null default 'draft' check(status in ('draft','accepted','active','superseded')),
  terms_snapshot jsonb not null,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(subscription_id,version_number),
  check(pin_operator_limit is null)
);

create table subscription_discounts (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  discount_type text not null check(discount_type in ('percentage','fixed_amount')),
  discount_base text not null check(discount_base in ('plan','addon','subtotal')),
  value numeric(14,4) not null check(value>0),
  reason text not null,
  starts_on date not null,
  ends_on date,
  permanent boolean not null default false,
  status text not null default 'approved' check(status in ('draft','approved','active','expired','revoked')),
  approved_by uuid not null,
  approved_at timestamptz not null,
  price_before_snapshot jsonb not null default '{}'::jsonb,
  price_final_snapshot jsonb not null default '{}'::jsonb,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check((permanent and ends_on is null) or (not permanent and ends_on is not null)),
  check(ends_on is null or ends_on>=starts_on)
);

create table subscription_addons (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  addon_code text not null check(addon_code='OPERATOR_PORTAL'),
  billing_mode text not null check(billing_mode in ('paid','included_negotiation','trial','promotion')),
  agreed_subtotal numeric(14,2) not null default 0,
  tax_rate numeric(7,6) not null default .16,
  tax numeric(14,2) not null,
  total numeric(14,2) not null,
  starts_at timestamptz not null,
  ends_at timestamptz,
  reason text not null,
  status text not null default 'scheduled' check(status in ('scheduled','trial','active','suspended','expired','canceled')),
  approved_by uuid not null,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check(ends_at is null or ends_at>starts_at),
  check(billing_mode<>'trial' or (ends_at is not null and ends_at<=starts_at+interval '3 months'))
);

create table subscription_administrator_memberships (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  auth_user_id uuid,
  email text not null,
  display_name text not null,
  role text not null default 'admin' check(role='admin'),
  status text not null default 'invited' check(status in ('invited','active','suspended','revoked')),
  invited_at timestamptz not null default now(),
  activated_at timestamptz,
  suspended_at timestamptz,
  revoked_at timestamptz,
  status_reason text not null default '',
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index subscription_admin_email_operational
  on subscription_administrator_memberships(subscription_id,lower(email))
  where status<>'revoked';
create unique index subscription_admin_user_operational
  on subscription_administrator_memberships(subscription_id,auth_user_id)
  where auth_user_id is not null and status<>'revoked';
create index subscription_admin_capacity_lookup
  on subscription_administrator_memberships(subscription_id,status)
  where status in ('invited','active');

create table subscription_limit_overrides (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  override_code text not null check(override_code in (
    'administrator_limit','vehicle_limit','fiscal_trip_limit',
    'operator_portal_access','subscription_access'
  )),
  integer_value integer check(integer_value is null or integer_value>=0),
  boolean_value boolean,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  reason text not null,
  status text not null default 'active' check(status in ('active','expired','revoked')),
  approved_by uuid not null,
  approved_at timestamptz not null,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check(ends_at>starts_at),
  check(
    (override_code in ('administrator_limit','vehicle_limit','fiscal_trip_limit')
      and integer_value is not null and boolean_value is null)
    or
    (override_code in ('operator_portal_access','subscription_access')
      and boolean_value is not null and integer_value is null)
  )
);
create index subscription_override_effective_lookup
  on subscription_limit_overrides(subscription_id,override_code,ends_at desc)
  where status='active';

create table commercial_fiscal_trip_ledger (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  tax_entity_id bigint not null references commercial_tax_entities(id),
  cfdi_id bigint,
  trip_id bigint,
  uuid_sat text,
  event_type text not null check(event_type in (
    'carta_porte_stamped','replacement_stamped','technical_compensation'
  )),
  quantity smallint not null check(quantity in (-1,1)),
  idempotency_key text not null unique,
  occurred_at timestamptz not null,
  period_month date not null,
  reason text not null default '',
  actor_user_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check(
    (event_type in ('carta_porte_stamped','replacement_stamped')
      and quantity=1 and uuid_sat is not null and char_length(trim(uuid_sat))>0)
    or
    (event_type='technical_compensation' and quantity=-1 and char_length(reason)>=3)
  )
);
create unique index commercial_fiscal_trip_uuid_consumption
  on commercial_fiscal_trip_ledger(subscription_id,upper(uuid_sat))
  where quantity=1;
create index commercial_fiscal_trip_period_lookup
  on commercial_fiscal_trip_ledger(subscription_id,period_month,occurred_at);

create table subscription_vehicle_state_events (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  vehicle_id bigint not null,
  from_active boolean,
  to_active boolean not null,
  reason text not null,
  actor_user_id uuid,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index subscription_vehicle_state_lookup
  on subscription_vehicle_state_events(subscription_id,vehicle_id,occurred_at desc);

create table subscription_renewals (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  current_term_version_id bigint not null references subscription_term_versions(id),
  proposed_term_version_id bigint references subscription_term_versions(id),
  renews_on date not null,
  reason text not null,
  status text not null default 'scheduled' check(status in ('scheduled','approved','completed','canceled')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table subscription_status_events (
  id bigint generated always as identity primary key,
  subscription_id bigint not null references commercial_subscriptions(id),
  from_status text not null,
  to_status text not null,
  reason text not null,
  actor_user_id uuid not null,
  expires_at timestamptz,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_quotes (
  id bigint generated always as identity primary key,
  folio text generated always as ('COT-'||lpad(id::text,8,'0')) stored,
  customer_id bigint not null references commercial_customers(id),
  tax_entity_id bigint,
  valid_until date not null,
  currency text not null default 'MXN',
  notes text not null default '',
  status text not null default 'draft' check(status in ('draft','internal_review','issued','accepted','rejected','expired','converted','canceled')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  foreign key(customer_id,tax_entity_id) references commercial_tax_entities(customer_id,id)
);

create table commercial_quote_versions (
  id bigint generated always as identity primary key,
  quote_id bigint not null references commercial_quotes(id),
  version_number integer not null,
  plan_version_id bigint not null references commercial_plan_versions(id),
  billing_period text not null,
  subtotal numeric(14,2) not null,
  discount numeric(14,2) not null default 0,
  tax_rate numeric(7,6) not null,
  implementation_subtotal numeric(14,2) not null default 0,
  operator_portal_subtotal numeric(14,2) not null default 0,
  gross_subtotal numeric(14,2) not null,
  net_subtotal numeric(14,2) not null,
  tax numeric(14,2) not null,
  total numeric(14,2) not null,
  payment_terms text not null,
  commercial_notes text not null default '',
  clause_version_ids jsonb not null default '[]'::jsonb,
  status text not null default 'draft' check(status in ('draft','issued','accepted','superseded')),
  quote_snapshot jsonb not null,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(quote_id,version_number)
);

create table service_orders (
  id bigint generated always as identity primary key,
  folio text generated always as ('OS-'||lpad(id::text,8,'0')) stored,
  customer_id bigint not null references commercial_customers(id),
  tax_entity_id bigint not null,
  subscription_id bigint references commercial_subscriptions(id),
  quote_version_id bigint references commercial_quote_versions(id),
  status text not null default 'draft' check(status in ('draft','issued','accepted','canceled')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  foreign key(customer_id,tax_entity_id) references commercial_tax_entities(customer_id,id)
);

create table service_order_versions (
  id bigint generated always as identity primary key,
  service_order_id bigint not null references service_orders(id),
  version_number integer not null,
  plan_version_id bigint not null references commercial_plan_versions(id),
  terms_snapshot jsonb not null,
  clause_version_ids jsonb not null default '[]'::jsonb,
  effective_from date,
  status text not null default 'draft' check(status in ('draft','issued','accepted','superseded')),
  order_snapshot jsonb not null,
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(service_order_id,version_number)
);

create table commercial_rate_cards (
  id bigint generated always as identity primary key,
  code text not null unique,
  name text not null,
  description text not null default '',
  status text not null default 'draft' check(status in ('draft','active','retired')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_rate_versions (
  id bigint generated always as identity primary key,
  rate_card_id bigint not null references commercial_rate_cards(id),
  version_number integer not null,
  billing_period text not null check(billing_period in ('monthly','annual')),
  subtotal numeric(14,2) not null,
  tax_rate numeric(7,6) not null,
  gross_subtotal numeric(14,2) not null,
  discount numeric(14,2) not null,
  net_subtotal numeric(14,2) not null,
  tax numeric(14,2) not null,
  total numeric(14,2) not null,
  effective_from date,
  status text not null default 'draft' check(status in ('draft','published','retired')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(rate_card_id,version_number)
);

create table commercial_clauses (
  id bigint generated always as identity primary key,
  code text not null unique,
  name text not null,
  category text not null default 'commercial',
  status text not null default 'draft' check(status in ('draft','active','retired')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table commercial_clause_versions (
  id bigint generated always as identity primary key,
  clause_id bigint not null references commercial_clauses(id),
  version_number integer not null,
  content text not null,
  content_sha256 text not null,
  effective_from date,
  status text not null default 'draft' check(status in ('draft','published','retired')),
  created_by uuid, updated_by uuid,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(clause_id,version_number)
);

create table commercial_audit_events (
  id bigint generated always as identity primary key,
  actor_user_id uuid not null,
  action text not null,
  entity_type text not null,
  entity_id text not null,
  before_data jsonb not null default '{}'::jsonb,
  after_data jsonb not null default '{}'::jsonb,
  reason text not null default '',
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create function protect_final_commercial_version() returns trigger language plpgsql as $$
begin
  if tg_op='DELETE' and old.status<>'draft' then
    raise exception 'Las versiones emitidas o publicadas son inmutables';
  elsif tg_op='UPDATE' and old.status<>'draft' then
    raise exception 'Las versiones emitidas o publicadas son inmutables';
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
grant usage,select on all sequences in schema public to authenticated;

create function protect_append_only_commercial_event() returns trigger language plpgsql as $$
begin
  raise exception 'El historial comercial es append-only';
end $$;
create trigger protect_prospect_activity before update or delete on commercial_prospect_activities
for each row execute function protect_append_only_commercial_event();
create trigger protect_prospect_stage_event before update or delete on commercial_prospect_stage_events
for each row execute function protect_append_only_commercial_event();
create trigger protect_commercial_audit_event before update or delete on commercial_audit_events
for each row execute function protect_append_only_commercial_event();
create trigger protect_fiscal_trip_ledger before update or delete on commercial_fiscal_trip_ledger
for each row execute function protect_append_only_commercial_event();
create trigger protect_vehicle_state_event before update or delete on subscription_vehicle_state_events
for each row execute function protect_append_only_commercial_event();

create function commercial_convert_prospect(
  p_prospect_id bigint, p_actor_user_id uuid, p_contractual_email text,
  p_authorized_contact text, p_reason text
) returns jsonb language plpgsql security invoker set search_path=public as $$
declare p commercial_prospects; customer commercial_customers;
begin
  select * into p from commercial_prospects where id=p_prospect_id for update;
  if not found then raise exception 'Prospecto no encontrado'; end if;
  if p.converted_customer_id is not null then
    select * into customer from commercial_customers where id=p.converted_customer_id;
    return jsonb_build_object('customer',to_jsonb(customer),'already_converted',true);
  end if;
  if p.stage not in ('qualified','proposal','negotiation','won') then
    raise exception 'El prospecto debe estar calificado';
  end if;
  insert into commercial_customers(
    name,contractual_email,authorized_contact,notes,status,created_by,updated_by
  ) values (
    coalesce(nullif(p.legal_name,''),p.business_name),p_contractual_email,
    p_authorized_contact,p.notes,'draft',p_actor_user_id,p_actor_user_id
  ) returning * into customer;
  update commercial_prospects set
    stage='won', converted_customer_id=customer.id, converted_at=now(),
    updated_by=p_actor_user_id, updated_at=now()
  where id=p.id;
  insert into commercial_prospect_stage_events(
    prospect_id,from_stage,to_stage,reason,actor_user_id
  ) values(p.id,p.stage,'won',p_reason,p_actor_user_id);
  insert into commercial_audit_events(
    actor_user_id,action,entity_type,entity_id,before_data,after_data,reason
  ) values(
    p_actor_user_id,'convert','commercial_prospect',p.id::text,to_jsonb(p),
    jsonb_build_object('customer',to_jsonb(customer),'prospect_stage','won'),p_reason
  );
  return jsonb_build_object('customer',to_jsonb(customer),'already_converted',false);
end $$;
revoke all on function commercial_convert_prospect(bigint,uuid,text,text,text) from public,authenticated;
grant execute on function commercial_convert_prospect(bigint,uuid,text,text,text) to service_role;

create function commercial_effective_administrator_limit(p_subscription_id bigint, p_at timestamptz)
returns integer language sql stable security invoker set search_path=public as $$
  select coalesce(
    (select integer_value from subscription_limit_overrides
      where subscription_id=p_subscription_id
        and override_code='administrator_limit' and status='active'
        and starts_at<=p_at and ends_at>p_at
      order by created_at desc,id desc limit 1),
    (select coalesce(term.administrator_limit,pv.administrator_limit)
      from commercial_subscriptions s
      join commercial_plan_versions pv on pv.id=s.plan_version_id
      left join lateral (
        select administrator_limit from subscription_term_versions
        where subscription_id=s.id and status in ('accepted','active')
        order by version_number desc limit 1
      ) term on true
      where s.id=p_subscription_id)
  )
$$;

create function commercial_invite_subscription_admin(
  p_subscription_id bigint, p_email text, p_display_name text,
  p_actor_user_id uuid, p_reason text
) returns jsonb language plpgsql security invoker set search_path=public as $$
declare capacity integer; occupied integer; member subscription_administrator_memberships;
begin
  perform 1 from commercial_subscriptions where id=p_subscription_id for update;
  if not found then raise exception 'Suscripción no encontrada'; end if;
  capacity := commercial_effective_administrator_limit(p_subscription_id,now());
  select count(*) into occupied from subscription_administrator_memberships
    where subscription_id=p_subscription_id and status in ('invited','active');
  if capacity is not null and occupied>=capacity then
    raise exception 'Límite de administradores alcanzado';
  end if;
  insert into subscription_administrator_memberships(
    subscription_id,email,display_name,status,status_reason,created_by,updated_by
  ) values(
    p_subscription_id,lower(trim(p_email)),p_display_name,'invited',p_reason,
    p_actor_user_id,p_actor_user_id
  ) returning * into member;
  insert into commercial_audit_events(
    actor_user_id,action,entity_type,entity_id,after_data,reason
  ) values(p_actor_user_id,'invite','subscription_administrator',member.id::text,to_jsonb(member),p_reason);
  return jsonb_build_object('membership',to_jsonb(member),'capacity',capacity,'occupied',occupied+1);
end $$;

create function commercial_change_admin_membership_status(
  p_membership_id bigint, p_target_status text, p_auth_user_id uuid,
  p_actor_user_id uuid, p_reason text, p_allow_last_admin boolean
) returns jsonb language plpgsql security invoker set search_path=public as $$
declare member subscription_administrator_memberships; before_row jsonb;
  active_count integer; capacity integer; occupied integer;
begin
  select * into member from subscription_administrator_memberships
    where id=p_membership_id for update;
  if not found then raise exception 'Membresía no encontrada'; end if;
  before_row := to_jsonb(member);
  if p_target_status not in ('active','suspended','revoked') then
    raise exception 'Estado inválido';
  end if;
  if p_target_status='active' then
    if coalesce(p_auth_user_id,member.auth_user_id) is null then
      raise exception 'La activación requiere usuario Auth';
    end if;
    if member.status not in ('invited','suspended') then raise exception 'Transición inválida'; end if;
    if member.status='suspended' then
      capacity := commercial_effective_administrator_limit(member.subscription_id,now());
      select count(*) into occupied from subscription_administrator_memberships
        where subscription_id=member.subscription_id and status in ('invited','active');
      if capacity is not null and occupied>=capacity then raise exception 'Límite de administradores alcanzado'; end if;
    end if;
  elsif member.status='active' then
    select count(*) into active_count from subscription_administrator_memberships
      where subscription_id=member.subscription_id and status='active';
    if active_count<=1 and not p_allow_last_admin then
      raise exception 'No se puede suspender o revocar al último administrador activo';
    end if;
  end if;
  update subscription_administrator_memberships set
    status=p_target_status,
    auth_user_id=coalesce(p_auth_user_id,auth_user_id),
    activated_at=case when p_target_status='active' then coalesce(activated_at,now()) else activated_at end,
    suspended_at=case when p_target_status='suspended' then now() else suspended_at end,
    revoked_at=case when p_target_status='revoked' then now() else revoked_at end,
    status_reason=p_reason,updated_by=p_actor_user_id,updated_at=now()
  where id=p_membership_id returning * into member;
  insert into commercial_audit_events(
    actor_user_id,action,entity_type,entity_id,before_data,after_data,reason
  ) values(p_actor_user_id,'status_transition','subscription_administrator',
    member.id::text,before_row,to_jsonb(member),p_reason);
  return jsonb_build_object('membership',to_jsonb(member));
end $$;

create function commercial_operator_portal_effective(p_subscription_id bigint,p_at timestamptz)
returns boolean language sql stable security invoker set search_path=public as $$
  select coalesce(
    (select boolean_value from subscription_limit_overrides
      where subscription_id=p_subscription_id
        and override_code='operator_portal_access' and status='active'
        and starts_at<=p_at and ends_at>p_at
      order by created_at desc,id desc limit 1),
    exists(select 1 from subscription_addons
      where subscription_id=p_subscription_id and addon_code='OPERATOR_PORTAL'
        and status in ('trial','active') and starts_at<=p_at
        and (ends_at is null or ends_at>p_at)),
    false
  )
$$;

revoke all on function commercial_effective_administrator_limit(bigint,timestamptz) from public,authenticated;
revoke all on function commercial_invite_subscription_admin(bigint,text,text,uuid,text) from public,authenticated;
revoke all on function commercial_change_admin_membership_status(bigint,text,uuid,uuid,text,boolean) from public,authenticated;
revoke all on function commercial_operator_portal_effective(bigint,timestamptz) from public,authenticated;
grant execute on function commercial_effective_administrator_limit(bigint,timestamptz) to service_role;
grant execute on function commercial_invite_subscription_admin(bigint,text,text,uuid,text) to service_role;
grant execute on function commercial_change_admin_membership_status(bigint,text,uuid,uuid,text,boolean) to service_role;
grant execute on function commercial_operator_portal_effective(bigint,timestamptz) to service_role;

create function commercial_fiscal_trip_capacity(p_subscription_id bigint,p_at timestamptz)
returns jsonb language sql stable security invoker set search_path=public as $$
  with base as (
    select coalesce(
      (select integer_value from subscription_limit_overrides
        where subscription_id=p_subscription_id and override_code='fiscal_trip_limit'
          and status='active' and starts_at<=p_at and ends_at>p_at
        order by created_at desc,id desc limit 1),
      (select coalesce(term.monthly_fiscal_trip_limit,pv.monthly_fiscal_trip_limit)
        from commercial_subscriptions s
        join commercial_plan_versions pv on pv.id=s.plan_version_id
        left join lateral (
          select monthly_fiscal_trip_limit from subscription_term_versions
          where subscription_id=s.id and status in ('accepted','active')
          order by version_number desc limit 1
        ) term on true where s.id=p_subscription_id)
    ) limit_value,
    date_trunc('month',p_at at time zone 'America/Mexico_City')::date period
  ), usage as (
    select coalesce(sum(quantity),0)::integer consumed from commercial_fiscal_trip_ledger,base
    where subscription_id=p_subscription_id and period_month=base.period
  )
  select jsonb_build_object(
    'period',base.period,'limit',base.limit_value,'consumed',usage.consumed,
    'remaining',case when base.limit_value is null then null else greatest(0,base.limit_value-usage.consumed) end,
    'percent',case when base.limit_value is null then 0 when base.limit_value=0 then 100
      else least(100,round(usage.consumed*100.0/base.limit_value,2)) end,
    'can_stamp',base.limit_value is null or usage.consumed<base.limit_value
  ) from base,usage
$$;

create function commercial_record_fiscal_trip(
  p_subscription_id bigint,p_tax_entity_id bigint,p_cfdi_id bigint,p_trip_id bigint,
  p_uuid_sat text,p_event_type text,p_occurred_at timestamptz,p_actor_user_id uuid,
  p_reason text,p_metadata jsonb
) returns jsonb language plpgsql security invoker set search_path=public as $$
declare row_event commercial_fiscal_trip_ledger; qty smallint; period date; capacity jsonb;
begin
  if nullif(trim(p_uuid_sat),'') is null then raise exception 'UUID requerido'; end if;
  if p_event_type not in ('carta_porte_stamped','replacement_stamped') then
    raise exception 'Evento de consumo inválido';
  end if;
  select * into row_event from commercial_fiscal_trip_ledger
    where idempotency_key='uuid:'||upper(trim(p_uuid_sat));
  if found then
    return jsonb_build_object('event',to_jsonb(row_event),'capacity',
      commercial_fiscal_trip_capacity(p_subscription_id,p_occurred_at),'idempotent',true);
  end if;
  perform 1 from commercial_subscriptions
    where id=p_subscription_id and tax_entity_id=p_tax_entity_id for update;
  if not found then raise exception 'Suscripción/RFC inválido'; end if;
  capacity:=commercial_fiscal_trip_capacity(p_subscription_id,p_occurred_at);
  if not coalesce((capacity->>'can_stamp')::boolean,false) then
    raise exception 'Límite mensual de viajes fiscales alcanzado';
  end if;
  qty:=1;
  period:=date_trunc('month',p_occurred_at at time zone 'America/Mexico_City')::date;
  insert into commercial_fiscal_trip_ledger(
    subscription_id,tax_entity_id,cfdi_id,trip_id,uuid_sat,event_type,quantity,
    idempotency_key,occurred_at,period_month,reason,actor_user_id,metadata
  ) values(
    p_subscription_id,p_tax_entity_id,p_cfdi_id,p_trip_id,upper(trim(p_uuid_sat)),
    p_event_type,qty,'uuid:'||upper(trim(p_uuid_sat)),p_occurred_at,period,
    coalesce(p_reason,''),p_actor_user_id,coalesce(p_metadata,'{}'::jsonb)
  ) on conflict(idempotency_key) do update set idempotency_key=excluded.idempotency_key
  returning * into row_event;
  return jsonb_build_object('event',to_jsonb(row_event),'capacity',
    commercial_fiscal_trip_capacity(p_subscription_id,p_occurred_at),'idempotent',false);
end $$;

revoke all on function commercial_fiscal_trip_capacity(bigint,timestamptz) from public,authenticated;
revoke all on function commercial_record_fiscal_trip(bigint,bigint,bigint,bigint,text,text,timestamptz,uuid,text,jsonb) from public,authenticated;
grant execute on function commercial_fiscal_trip_capacity(bigint,timestamptz) to service_role;
grant execute on function commercial_record_fiscal_trip(bigint,bigint,bigint,bigint,text,text,timestamptz,uuid,text,jsonb) to service_role;

create trigger protect_plan_version before update or delete on commercial_plan_versions
for each row execute function protect_final_commercial_version();
create trigger protect_price_version before update or delete on commercial_price_versions
for each row execute function protect_final_commercial_version();
create trigger protect_subscription_terms before update or delete on subscription_term_versions
for each row execute function protect_final_commercial_version();
create trigger protect_quote_version before update or delete on commercial_quote_versions
for each row execute function protect_final_commercial_version();
create trigger protect_order_version before update or delete on service_order_versions
for each row execute function protect_final_commercial_version();
create trigger protect_rate_version before update or delete on commercial_rate_versions
for each row execute function protect_final_commercial_version();
create trigger protect_clause_version before update or delete on commercial_clause_versions
for each row execute function protect_final_commercial_version();

-- Backend-only: authenticated cannot read or mutate directly.
do $$
declare t text;
begin
  foreach t in array array[
    'commercial_customers','commercial_prospects','commercial_prospect_contacts',
    'commercial_prospect_activities','commercial_prospect_tasks',
    'commercial_prospect_stage_events','commercial_tax_entities','commercial_plans',
    'commercial_plan_versions','commercial_price_versions',
    'commercial_subscriptions','subscription_term_versions',
    'subscription_discounts','subscription_addons',
    'subscription_administrator_memberships','subscription_limit_overrides',
    'commercial_fiscal_trip_ledger','subscription_vehicle_state_events',
    'subscription_renewals',
    'subscription_status_events','commercial_quotes',
    'commercial_quote_versions','service_orders','service_order_versions',
    'commercial_rate_cards','commercial_rate_versions',
    'commercial_clauses','commercial_clause_versions',
    'commercial_audit_events'
  ] loop
    execute format('alter table %I enable row level security',t);
    execute format('grant select,insert,update,delete on %I to authenticated',t);
    execute format('create policy %I on %I for all to authenticated using (false) with check (false)',t||'_backend_only',t);
  end loop;
end $$;
grant all on all tables in schema public to service_role;
grant usage,select on all sequences in schema public to service_role;

-- Borradores editables iniciales; no están asociados a clientes reales.
insert into commercial_plans(code,name,commercializable,legacy,grandfathered)
values
('ESENCIAL','Esencial',true,false,false),
('OPERACION','Operación',true,false,false),
('FLOTILLA','Flotilla',true,false,false),
('ENTERPRISE','Enterprise',true,false,false),
('LEGACY_2800','Legado $2,800',false,true,true);

insert into commercial_plan_versions
  (plan_id,version_number,vehicle_limit,monthly_fiscal_trip_limit,administrator_limit,pin_operator_limit,status,limits_snapshot)
select id,1,
  case code when 'ESENCIAL' then 5 when 'OPERACION' then 20 when 'FLOTILLA' then 60 end,
  case code when 'ESENCIAL' then 50 when 'OPERACION' then 200 when 'FLOTILLA' then 600 end,
  case code when 'ESENCIAL' then 1 when 'OPERACION' then 2 when 'FLOTILLA' then 3 end,
  null,'draft','{}'::jsonb
from commercial_plans;

insert into commercial_price_versions
  (plan_version_id,billing_period,subtotal,tax_rate,tax,total,currency,status)
select version.id,'monthly',price,.16,round(price*.16,2),round(price*1.16,2),'MXN','draft'
from commercial_plan_versions version
join commercial_plans plan on plan.id=version.plan_id
cross join lateral (
  select case plan.code
    when 'ESENCIAL' then 5900::numeric
    when 'OPERACION' then 11900::numeric
    when 'FLOTILLA' then 24900::numeric
    when 'LEGACY_2800' then 2800::numeric
  end price
) configured
where configured.price is not null;
