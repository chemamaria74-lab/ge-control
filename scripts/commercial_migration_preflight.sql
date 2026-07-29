-- Sólo lectura. Ejecutar antes de aplicar la migración comercial.

select table_name
from information_schema.tables
where table_schema='public'
  and table_name in (
    'commercial_customers','commercial_tax_entities','commercial_subscriptions',
    'commercial_fiscal_trip_ledger','subscription_administrator_memberships'
  )
order by table_name;

select count(*) as perfiles_sin_tenant
from public.perfiles_empresa
where tenant_id is null;

select count(*) as accesos_activos_sin_scope
from public.user_sections
where status='active' and (tenant_id is null or perfil_id is null);

select pe.id,pe.tenant_id,pe.rfc,pe.nombre
from public.perfiles_empresa pe
where pe.tenant_id is null
order by pe.id;

select count(*) as cartas_porte_con_uuid
from public.tr_cfdi
where tipo_cfdi='T' and nullif(trim(uuid_sat),'') is not null;

select count(distinct upper(trim(uuid_sat))) as uuid_carta_porte_unicos
from public.tr_cfdi
where tipo_cfdi='T' and nullif(trim(uuid_sat),'') is not null;

select perfil_id,count(*) as vehiculos_activos
from public.tr_vehiculos
where activo=true and deleted_at is null
group by perfil_id
order by perfil_id;
