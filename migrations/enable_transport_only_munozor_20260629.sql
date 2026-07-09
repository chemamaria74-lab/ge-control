-- GE CONTROL - Habilitar munozor@yahoo.com solo para Transporte.
-- Idempotente: crea/actualiza tenant, perfil, companies, subscription y user_sections.

begin;

do $$
declare
  v_user_id uuid := '24fed2a1-281b-4e4e-9dde-b99ecf8b46d8'::uuid;
  v_email text := 'munozor@yahoo.com';
  v_tenant_id uuid := v_user_id;
  v_perfil_id bigint;
begin
  if not exists (
    select 1
    from auth.users
    where id = v_user_id
      and lower(email) = lower(v_email)
  ) then
    raise exception 'No existe auth.users id=% email=%', v_user_id, v_email;
  end if;

  insert into public.tenants (id, name, status, updated_at)
  values (v_tenant_id, 'RAFAEL ORNELAS MUÑOZ', 'active', now())
  on conflict (id) do update
    set name = excluded.name,
        status = 'active',
        updated_at = now();

  update public.user_sections
  set status = 'inactive'
  where user_id = v_user_id
    and section <> 'transporte'
    and coalesce(status, 'active') <> 'inactive';

  select id
    into v_perfil_id
  from public.perfiles_empresa
  where user_id = v_user_id
    and rfc = 'OEMR721229767'
    and descripcion ilike '%[module:transporte]%'
  order by activo desc, updated_at desc nulls last, id
  limit 1;

  if v_perfil_id is null then
    insert into public.perfiles_empresa (
      user_id,
      tenant_id,
      nombre,
      rfc,
      descripcion,
      activo,
      created_at,
      updated_at
    )
    values (
      v_user_id,
      v_tenant_id,
      'RAFAEL ORNELAS MUÑOZ',
      'OEMR721229767',
      '[module:transporte] Actividad principal: Otro autotransporte foráneo de carga general.',
      true,
      now(),
      now()
    )
    returning id into v_perfil_id;
  else
    update public.perfiles_empresa
    set tenant_id = v_tenant_id,
        nombre = 'RAFAEL ORNELAS MUÑOZ',
        rfc = 'OEMR721229767',
        descripcion = case
          when descripcion ilike '%[module:transporte]%' then descripcion
          else concat('[module:transporte] ', coalesce(descripcion, ''))
        end,
        activo = true,
        updated_at = now()
    where id = v_perfil_id;
  end if;

  insert into public.companies (id, tenant_id, name, rfc, active, updated_at)
  values (v_perfil_id, v_tenant_id, 'RAFAEL ORNELAS MUÑOZ', 'OEMR721229767', true, now())
  on conflict (id) do update
    set tenant_id = excluded.tenant_id,
        name = excluded.name,
        rfc = excluded.rfc,
        active = true,
        updated_at = now();

  if exists (
    select 1
    from public.subscriptions
    where tenant_id = v_tenant_id
      and status = 'active'
  ) then
    update public.subscriptions
    set plan_name = 'Transporte',
        max_companies = 1,
        status = 'active',
        limits_json = jsonb_build_object(
          'companies', 1,
          'gas_lp', jsonb_build_object(
            'enabled', false,
            'companies', 0,
            'assistants', 0,
            'can_invoice', false,
            'can_view_reports', false,
            'can_generate_json', false,
            'can_upload_xml_excel', false
          ),
          'transporte', jsonb_build_object(
            'enabled', true,
            'companies', 1,
            'admins', 0,
            'operators', 1,
            'vehicles', null,
            'can_stamp_carta_porte', true,
            'can_invoice_service', true,
            'can_use_liquidaciones', true
          ),
          'gasolineras', jsonb_build_object(
            'enabled', false,
            'stations', 0,
            'users', 0,
            'can_view_map', false,
            'can_view_radar', false,
            'can_view_reports', false,
            'can_use_operations', false
          )
        ),
        notes_internal = 'Alta inicial solicitada para munozor@yahoo.com; acceso limitado a Transporte.',
        updated_at = now()
    where tenant_id = v_tenant_id
      and status = 'active';
  else
    insert into public.subscriptions (
      tenant_id,
      plan_name,
      max_companies,
      status,
      limits_json,
      notes_internal,
      updated_at
    )
    values (
      v_tenant_id,
      'Transporte',
      1,
      'active',
      jsonb_build_object(
        'companies', 1,
        'gas_lp', jsonb_build_object(
          'enabled', false,
          'companies', 0,
          'assistants', 0,
          'can_invoice', false,
          'can_view_reports', false,
          'can_generate_json', false,
          'can_upload_xml_excel', false
        ),
        'transporte', jsonb_build_object(
          'enabled', true,
          'companies', 1,
          'admins', 0,
          'operators', 1,
          'vehicles', null,
          'can_stamp_carta_porte', true,
          'can_invoice_service', true,
          'can_use_liquidaciones', true
        ),
        'gasolineras', jsonb_build_object(
          'enabled', false,
          'stations', 0,
          'users', 0,
          'can_view_map', false,
          'can_view_radar', false,
          'can_view_reports', false,
          'can_use_operations', false
        )
      ),
      'Alta inicial solicitada para munozor@yahoo.com; acceso limitado a Transporte.',
      now()
    );
  end if;

  insert into public.user_sections (
    user_id,
    section,
    role,
    status,
    display_name,
    tenant_id,
    perfil_id,
    created_at
  )
  values (
    v_user_id,
    'transporte',
    'user',
    'active',
    'RAFAEL ORNELAS MUÑOZ',
    v_tenant_id,
    v_perfil_id,
    now()
  )
  on conflict (user_id, section) do update
    set role = 'user',
        status = 'active',
        display_name = 'RAFAEL ORNELAS MUÑOZ',
        tenant_id = v_tenant_id,
        perfil_id = v_perfil_id;
end $$;

commit;
