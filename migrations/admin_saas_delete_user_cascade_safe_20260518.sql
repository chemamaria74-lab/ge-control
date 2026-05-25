-- GE CONTROL - Eliminacion segura de usuarios Supabase Auth
-- Aplica en Supabase SQL editor antes de usar Superadmin > Eliminar seguro.
-- confirm=false solo previsualiza conteos; confirm=true limpia/transferiere referencias y borra auth.users.

create or replace function public.delete_user_cascade_safe(
  p_target_user_id uuid,
  p_actor_user_id uuid,
  p_confirm boolean default false,
  p_transfer_user_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_counts jsonb := '{}'::jsonb;
  v_deleted jsonb := '{}'::jsonb;
  v_transferred jsonb := '{}'::jsonb;
  v_profile_ids bigint[] := '{}'::bigint[];
  v_tenant_ids uuid[] := '{}'::uuid[];
  v_count bigint;
  v_table regclass;
  v_table_name text;
  v_schema_name text;
  v_short_table_name text;
  v_col text;
  v_col_udt text;
  v_sql text;
begin
  if p_target_user_id is null then
    raise exception 'p_target_user_id requerido';
  end if;
  if p_transfer_user_id is not null and p_transfer_user_id = p_target_user_id then
    raise exception 'El receptor debe ser diferente al usuario eliminado';
  end if;

  if p_confirm and not exists (select 1 from auth.users where id = p_actor_user_id) then
    raise exception 'Actor no existe en auth.users';
  end if;
  if p_transfer_user_id is not null and not exists (select 1 from auth.users where id = p_transfer_user_id) then
    raise exception 'Receptor no existe en auth.users';
  end if;

  select coalesce(array_agg(id), '{}'::bigint[])
    into v_profile_ids
  from public.perfiles_empresa
  where user_id::text = p_target_user_id::text;

  select coalesce(array_agg(distinct tenant_id), '{}'::uuid[])
    into v_tenant_ids
  from (
    select tenant_id from public.user_sections
    where user_id::text = p_target_user_id::text and tenant_id is not null
    union
    select tenant_id from public.perfiles_empresa
    where user_id::text = p_target_user_id::text and tenant_id is not null
  ) t;

  -- Conteos por referencias directas al usuario.
  for v_table_name, v_col in
    select c.table_name, c.column_name
    from information_schema.columns c
    join information_schema.tables t
      on t.table_schema = c.table_schema
     and t.table_name = c.table_name
    where c.table_schema = 'public'
      and t.table_type = 'BASE TABLE'
      and c.column_name in ('user_id', 'owner_user_id', 'requested_by', 'created_by', 'updated_by')
    order by c.table_name, c.column_name
  loop
    v_sql := format('select count(*) from public.%I where %I::text = $1', v_table_name, v_col);
    execute v_sql into v_count using p_target_user_id::text;
    if v_count > 0 then
      v_counts := v_counts || jsonb_build_object(v_table_name || '.' || v_col, v_count);
    end if;
  end loop;

  -- Conteos por perfil/empresa del usuario.
  if array_length(v_profile_ids, 1) is not null then
    for v_table_name in
      select c.table_name
      from information_schema.columns c
      join information_schema.tables t
        on t.table_schema = c.table_schema
       and t.table_name = c.table_name
      where c.table_schema = 'public'
        and t.table_type = 'BASE TABLE'
        and c.column_name = 'perfil_id'
      order by c.table_name
    loop
      v_sql := format('select count(*) from public.%I where perfil_id = any($1)', v_table_name);
      execute v_sql into v_count using v_profile_ids;
      if v_count > 0 then
        v_counts := v_counts || jsonb_build_object(v_table_name || '.perfil_id', v_count);
      end if;
    end loop;
  end if;

  v_counts := v_counts || jsonb_build_object(
    'auth.users', case when exists (select 1 from auth.users where id = p_target_user_id) then 1 else 0 end,
    'tenant_ids', coalesce(array_length(v_tenant_ids, 1), 0),
    'perfil_ids', coalesce(array_length(v_profile_ids, 1), 0)
  );

  if not p_confirm then
    return jsonb_build_object(
      'ok', true,
      'mode', 'preview',
      'user', jsonb_build_object('id', p_target_user_id),
      'counts', v_counts,
      'tenant_ids', to_jsonb(v_tenant_ids),
      'perfil_ids', to_jsonb(v_profile_ids),
      'requires_transfer', false
    );
  end if;

  -- Sesiones internas primero para evitar FKs sobre internal_users.
  if to_regclass('public.internal_user_sessions') is not null
     and to_regclass('public.internal_users') is not null then
    delete from public.internal_user_sessions s
    using public.internal_users u
    where s.internal_user_id = u.id
      and u.owner_user_id::text = p_target_user_id::text;
    get diagnostics v_count = row_count;
    if v_count > 0 then
      v_deleted := v_deleted || jsonb_build_object('internal_user_sessions.by_owner', v_count);
    end if;
  end if;

  if p_transfer_user_id is not null then
    -- Conserva datos del cliente y cambia propietario humano.
    for v_table_name, v_col, v_col_udt in
      select c.table_name, c.column_name, c.udt_name
      from information_schema.columns c
      join information_schema.tables t
        on t.table_schema = c.table_schema
       and t.table_name = c.table_name
      where c.table_schema = 'public'
        and t.table_type = 'BASE TABLE'
        and c.column_name in ('user_id', 'owner_user_id', 'requested_by', 'created_by', 'updated_by')
      order by c.table_name, c.column_name
    loop
      if v_col_udt = 'uuid' then
        v_sql := format('update public.%I set %I = $1::uuid where %I::text = $2', v_table_name, v_col, v_col);
      else
        v_sql := format('update public.%I set %I = $1::text where %I::text = $2', v_table_name, v_col, v_col);
      end if;
      execute v_sql using p_transfer_user_id, p_target_user_id::text;
      get diagnostics v_count = row_count;
      if v_count > 0 then
        v_transferred := v_transferred || jsonb_build_object(v_table_name || '.' || v_col, v_count);
      end if;
    end loop;
  else
    -- Elimina datos del usuario de tablas hijas por perfil primero.
    foreach v_table_name in array array[
      'public.internal_user_sessions',
      'public.fiscal_document_events',
      'public.invoice_cancellations',
      'public.xml_versions',
      'public.pac_responses',
      'public.pac_requests',
      'public.cfdi_sat_inbox',
      'public.detected_loads',
      'public.sat_sync_jobs',
      'public.sat_credentials',
      'public.user_facilities',
      'public.providers',
      'public.records',
      'public.reports',
      'public.movimientos',
      'public.gas_lp_choferes',
      'public.gas_lp_vehiculos',
      'public.gas_lp_rutas',
      'public.gas_lp_clientes_facturacion',
      'public.gas_lp_facturas',
      'public.gas_lp_facturas_servicio',
      'public.gaso_precio_historico',
      'public.gaso_cfdi',
      'public.gaso_cfdi_compras',
      'public.gaso_ventas',
      'public.gaso_alertas',
      'public.gaso_estaciones',
      'public.tr_cliente_contactos',
      'public.tr_liquidacion_items',
      'public.tr_liquidaciones',
      'public.tr_gastos_viaje',
      'public.tr_viaje_documentos',
      'public.tr_viaje_eventos',
      'public.tr_operador_accesos',
      'public.tr_facturas_servicio_cartas',
      'public.tr_facturas_servicio',
      'public.tr_cfdi',
      'public.tr_viajes',
      'public.tr_tarifas',
      'public.tr_importaciones',
      'public.tr_vehiculo_seguros',
      'public.tr_vehiculo_permisos',
      'public.tr_vehiculo_remolques',
      'public.tr_permisos_operacion',
      'public.tr_remolques',
      'public.tr_centros_emisores',
      'public.tr_destinos',
      'public.tr_origenes',
      'public.tr_choferes',
      'public.tr_vehiculos',
      'public.tr_rutas',
      'public.tr_clientes',
      'public.gaso_settings',
      'public.tr_settings',
      'public.zc_settings',
      'public.settings_audit',
      'public.internal_users',
      'public.user_sections',
      'public.user_licenses',
      'public.perfiles_empresa'
    ]
    loop
      v_table := to_regclass(v_table_name);
      if v_table is null then
        continue;
      end if;
      v_schema_name := split_part(v_table_name, '.', 1);
      v_short_table_name := split_part(v_table_name, '.', 2);
      if exists (
        select 1 from information_schema.columns
        where table_schema = v_schema_name
          and table_name = v_short_table_name
          and column_name = 'perfil_id'
      ) and array_length(v_profile_ids, 1) is not null then
        v_sql := format('delete from %s where perfil_id = any($1)', v_table);
        execute v_sql using v_profile_ids;
        get diagnostics v_count = row_count;
        if v_count > 0 then
          v_deleted := v_deleted || jsonb_build_object(v_table_name || '.perfil_id', v_count);
        end if;
      end if;

      if exists (
        select 1 from information_schema.columns
        where table_schema = v_schema_name
          and table_name = v_short_table_name
          and column_name = 'user_id'
      ) then
        v_sql := format('delete from %s where user_id::text = $1', v_table);
        execute v_sql using p_target_user_id::text;
        get diagnostics v_count = row_count;
        if v_count > 0 then
          v_deleted := v_deleted || jsonb_build_object(v_table_name || '.user_id', v_count);
        end if;
      end if;

      if exists (
        select 1 from information_schema.columns
        where table_schema = v_schema_name
          and table_name = v_short_table_name
          and column_name = 'owner_user_id'
      ) then
        v_sql := format('delete from %s where owner_user_id::text = $1', v_table);
        execute v_sql using p_target_user_id::text;
        get diagnostics v_count = row_count;
        if v_count > 0 then
          v_deleted := v_deleted || jsonb_build_object(v_table_name || '.owner_user_id', v_count);
        end if;
      end if;
    end loop;

    -- Barrido final para tablas nuevas con columnas de usuario que no estaban en la lista ordenada.
    for v_table_name, v_col in
      select c.table_name, c.column_name
      from information_schema.columns c
      join information_schema.tables t
        on t.table_schema = c.table_schema
       and t.table_name = c.table_name
      where c.table_schema = 'public'
        and t.table_type = 'BASE TABLE'
        and c.column_name in ('user_id', 'owner_user_id', 'requested_by', 'created_by', 'updated_by')
      order by c.table_name, c.column_name
    loop
      v_sql := format('delete from public.%I where %I::text = $1', v_table_name, v_col);
      execute v_sql using p_target_user_id::text;
      get diagnostics v_count = row_count;
      if v_count > 0 then
        v_deleted := v_deleted || jsonb_build_object(v_table_name || '.' || v_col || '.sweep', v_count);
      end if;
    end loop;

    -- Borra tenants solo si ya no tienen usuarios/perfiles asociados.
    if array_length(v_tenant_ids, 1) is not null then
      delete from public.companies c
      where c.tenant_id = any(v_tenant_ids)
        and not exists (select 1 from public.user_sections us where us.tenant_id = c.tenant_id)
        and not exists (select 1 from public.perfiles_empresa pe where pe.tenant_id = c.tenant_id);
      get diagnostics v_count = row_count;
      if v_count > 0 then
        v_deleted := v_deleted || jsonb_build_object('companies.orphan_tenant', v_count);
      end if;

      delete from public.subscriptions s
      where s.tenant_id = any(v_tenant_ids)
        and not exists (select 1 from public.user_sections us where us.tenant_id = s.tenant_id)
        and not exists (select 1 from public.perfiles_empresa pe where pe.tenant_id = s.tenant_id);
      get diagnostics v_count = row_count;
      if v_count > 0 then
        v_deleted := v_deleted || jsonb_build_object('subscriptions.orphan_tenant', v_count);
      end if;

      delete from public.tenants t
      where t.id = any(v_tenant_ids)
        and not exists (select 1 from public.user_sections us where us.tenant_id = t.id)
        and not exists (select 1 from public.perfiles_empresa pe where pe.tenant_id = t.id)
        and not exists (select 1 from public.companies c where c.tenant_id = t.id)
        and not exists (select 1 from public.subscriptions s where s.tenant_id = t.id);
      get diagnostics v_count = row_count;
      if v_count > 0 then
        v_deleted := v_deleted || jsonb_build_object('tenants.orphan', v_count);
      end if;
    end if;
  end if;

  delete from auth.users where id = p_target_user_id;
  get diagnostics v_count = row_count;

  return jsonb_build_object(
    'ok', true,
    'mode', 'deleted',
    'user', jsonb_build_object('id', p_target_user_id),
    'counts_before', v_counts,
    'deleted', v_deleted,
    'transferred', v_transferred,
    'auth_deleted', v_count > 0
  );
end;
$$;

revoke all on function public.delete_user_cascade_safe(uuid, uuid, boolean, uuid) from public;
grant execute on function public.delete_user_cascade_safe(uuid, uuid, boolean, uuid) to service_role;
