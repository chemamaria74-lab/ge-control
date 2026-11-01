-- Completa el espejo de entrada para traspasos históricos cuyo destino quedó en metadata.
-- No modifica ni elimina facturas ni registros fuente.
insert into public.gas_lp_movement_ledger (
 source_key,source_table,source_id,source_role,source_priority,user_id,tenant_id,perfil_id,facility_id,effective_at,
 movement_type,direction,liters,document_uuid,counterparty_rfc,counterparty_name,amount,status,
 source_snapshot,metadata,source_created_at,source_updated_at,last_synced_at
)
select 'gas_lp_facturas:'||f.id::text||':destination','gas_lp_facturas',f.id,'destination',5,
 f.user_id::text,f.tenant_id,f.perfil_id,
 coalesce(f.destino_facility_id,private.glp_safe_bigint(f.metadata->>'destino_facility_id'),private.glp_safe_bigint(f.metadata->>'instalacion_destino_id')),
 coalesce(private.glp_safe_timestamptz(f.metadata->>'fecha_operacion',null),f.fecha_emision,f.fecha_timbrado,f.created_at,now()),
 'transfer_in',1,f.volumen_litros,nullif(upper(coalesce(nullif(f.uuid_sat,''),f.record_uuid)),''),
 f.rfc_receptor,coalesce(f.receptor_nombre,f.cliente_nombre),coalesce(f.total,f.importe),
 case when lower(coalesce(f.status,'')) like 'cancel%' then 'cancelled' else 'active' end,
 to_jsonb(f),f.metadata,f.created_at,f.updated_at,now()
from public.gas_lp_facturas f
where f.volumen_litros>0 and upper(coalesce(f.tipo_comprobante,''))<>'T'
and (coalesce(f.is_transfer,false) or lower(coalesce(f.tipo_operacion,''))='traspaso'
 or lower(coalesce(f.metadata->>'tipo_operacion',''))='traspaso'
 or lower(coalesce(f.metadata->>'is_transfer','')) in ('true','t','1','yes'))
and coalesce(f.destino_facility_id,private.glp_safe_bigint(f.metadata->>'destino_facility_id'),private.glp_safe_bigint(f.metadata->>'instalacion_destino_id')) is not null
on conflict(source_key) do update set facility_id=excluded.facility_id,effective_at=excluded.effective_at,
 movement_type=excluded.movement_type,direction=excluded.direction,liters=excluded.liters,document_uuid=excluded.document_uuid,
 status=excluded.status,source_snapshot=excluded.source_snapshot,metadata=excluded.metadata,source_updated_at=excluded.source_updated_at,last_synced_at=now();
analyze public.gas_lp_movement_ledger;
