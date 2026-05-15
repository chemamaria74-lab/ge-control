-- GE CONTROL - Sprint seguridad: RLS + Storage privado
-- Ejecutar en Supabase SQL Editor.
-- Objetivo: proteger datos fiscales/operativos por auth.uid(), user_id y paths privados.

-- 1) Buckets privados para documentos fiscales/operativos.
insert into storage.buckets (id, name, public)
values ('transport-documents', 'transport-documents', false)
on conflict (id) do update set public = false;

alter table if exists public.tr_operador_accesos
  add column if not exists expires_at timestamptz,
  add column if not exists last_used_at timestamptz;

-- 2) Storage policies: cada usuario solo puede operar dentro de su carpeta user_id.
-- Rutas esperadas: {user_id}/{perfil_id}/{viaje_id}/...
drop policy if exists "ge_transport_docs_select_own_path" on storage.objects;
drop policy if exists "ge_transport_docs_insert_own_path" on storage.objects;
drop policy if exists "ge_transport_docs_update_own_path" on storage.objects;
drop policy if exists "ge_transport_docs_delete_own_path" on storage.objects;

create policy "ge_transport_docs_select_own_path"
on storage.objects for select to authenticated
using (
  bucket_id = 'transport-documents'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "ge_transport_docs_insert_own_path"
on storage.objects for insert to authenticated
with check (
  bucket_id = 'transport-documents'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "ge_transport_docs_update_own_path"
on storage.objects for update to authenticated
using (
  bucket_id = 'transport-documents'
  and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
  bucket_id = 'transport-documents'
  and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "ge_transport_docs_delete_own_path"
on storage.objects for delete to authenticated
using (
  bucket_id = 'transport-documents'
  and (storage.foldername(name))[1] = auth.uid()::text
);

-- 3) RLS en tablas sensibles de Transporte.
do $$
declare
  t text;
begin
  foreach t in array array[
    'tr_viajes',
    'tr_cfdi',
    'tr_facturas_servicio',
    'tr_facturas_servicio_cartas',
    'tr_choferes',
    'tr_vehiculos',
    'tr_rutas',
    'tr_clientes',
    'tr_settings',
    'tr_covol_reports',
    'tr_viaje_eventos',
    'tr_viaje_documentos',
    'tr_tarifas',
    'tr_gastos_viaje',
    'tr_liquidaciones',
    'tr_liquidacion_items',
    'tr_notificaciones',
    'tr_operador_accesos',
    'tr_importaciones'
  ] loop
    if to_regclass('public.' || t) is not null then
      execute format('alter table public.%I enable row level security', t);
      execute format('drop policy if exists %I on public.%I', 'ge_' || t || '_own_rows', t);
      execute format(
        'create policy %I on public.%I for all to authenticated using (user_id::text = auth.uid()::text) with check (user_id::text = auth.uid()::text)',
        'ge_' || t || '_own_rows',
        t
      );
    end if;
  end loop;
end $$;

-- 4) RLS en tablas sensibles de Gasolineras.
do $$
declare
  t text;
begin
  foreach t in array array[
    'gaso_settings',
    'gaso_estaciones',
    'gaso_precio_historico',
    'gaso_cfdi',
    'gaso_cfdi_compras',
    'gaso_ventas',
    'gaso_alertas'
  ] loop
    if to_regclass('public.' || t) is not null then
      execute format('alter table public.%I enable row level security', t);
      execute format('drop policy if exists %I on public.%I', 'ge_' || t || '_own_rows', t);
      execute format(
        'create policy %I on public.%I for all to authenticated using (user_id::text = auth.uid()::text) with check (user_id::text = auth.uid()::text)',
        'ge_' || t || '_own_rows',
        t
      );
    end if;
  end loop;
end $$;

-- 5) RLS en tablas compartidas sensibles.
do $$
declare
  t text;
begin
  foreach t in array array[
    'zc_settings',
    'providers',
    'user_facilities',
    'reports',
    'records',
    'user_sections'
  ] loop
    if to_regclass('public.' || t) is not null then
      execute format('alter table public.%I enable row level security', t);
      execute format('drop policy if exists %I on public.%I', 'ge_' || t || '_own_rows', t);
      execute format(
        'create policy %I on public.%I for all to authenticated using (user_id::text = auth.uid()::text) with check (user_id::text = auth.uid()::text)',
        'ge_' || t || '_own_rows',
        t
      );
    end if;
  end loop;
end $$;

-- 6) Índices de aislamiento/consulta por perfil.
do $$
begin
  if to_regclass('public.tr_viaje_documentos') is not null then
    create index if not exists idx_tr_docs_user_perfil_viaje
      on public.tr_viaje_documentos(user_id, perfil_id, viaje_id);
  end if;
  if to_regclass('public.tr_cfdi') is not null then
    create index if not exists idx_tr_cfdi_user_perfil_uuid
      on public.tr_cfdi(user_id, perfil_id, uuid_sat);
  end if;
  if to_regclass('public.tr_operador_accesos') is not null then
    create index if not exists idx_tr_operator_active_hash
      on public.tr_operador_accesos(token_hash, status);
  end if;
  if to_regclass('public.gaso_cfdi') is not null then
    create index if not exists idx_gaso_cfdi_user_perfil_uuid
      on public.gaso_cfdi(user_id, perfil_id, uuid_sat);
  end if;
end $$;
