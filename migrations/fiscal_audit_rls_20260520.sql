-- GE CONTROL - RLS para auditoría fiscal/PAC/XML.
-- Seguro e idempotente:
-- - Backend/service_role conserva lectura/escritura porque bypasses RLS.
-- - anon no tiene políticas.
-- - authenticated solo puede leer filas propias o del tenant/perfil asignado.
-- - authenticated no puede insertar/actualizar/borrar directo.

alter table if exists public.sat_catalog_cache enable row level security;
alter table if exists public.pac_requests enable row level security;
alter table if exists public.pac_responses enable row level security;
alter table if exists public.xml_versions enable row level security;
alter table if exists public.invoice_cancellations enable row level security;

-- Catálogos/cache fiscal: no se exponen directo al cliente por ahora.
drop policy if exists sat_catalog_cache_no_client_access on public.sat_catalog_cache;
create policy sat_catalog_cache_no_client_access
  on public.sat_catalog_cache
  for all to authenticated
  using (false)
  with check (false);

-- Intentos PAC: lectura limitada al propio usuario o tenant/perfil asignado.
drop policy if exists pac_requests_scoped_read on public.pac_requests;
create policy pac_requests_scoped_read
  on public.pac_requests
  for select to authenticated
  using (
    user_id::text = auth.uid()::text
    or exists (
      select 1
      from public.user_sections us
      where us.user_id::text = auth.uid()::text
        and coalesce(us.status, 'active') = 'active'
        and (
          (pac_requests.tenant_id is not null and us.tenant_id = pac_requests.tenant_id)
          or (
            pac_requests.perfil_id is not null
            and us.perfil_id is not null
            and us.perfil_id = pac_requests.perfil_id
          )
        )
    )
  );

-- Respuestas PAC: se leen solo si el request relacionado es visible al usuario.
drop policy if exists pac_responses_scoped_read on public.pac_responses;
create policy pac_responses_scoped_read
  on public.pac_responses
  for select to authenticated
  using (
    exists (
      select 1
      from public.pac_requests pr
      where pr.id = pac_responses.request_id
        and (
          pr.user_id::text = auth.uid()::text
          or exists (
            select 1
            from public.user_sections us
            where us.user_id::text = auth.uid()::text
              and coalesce(us.status, 'active') = 'active'
              and (
                (pr.tenant_id is not null and us.tenant_id = pr.tenant_id)
                or (
                  pr.perfil_id is not null
                  and us.perfil_id is not null
                  and us.perfil_id = pr.perfil_id
                )
              )
          )
        )
    )
  );

-- Versiones XML: lectura limitada al propio usuario o tenant/perfil asignado.
drop policy if exists xml_versions_scoped_read on public.xml_versions;
create policy xml_versions_scoped_read
  on public.xml_versions
  for select to authenticated
  using (
    user_id::text = auth.uid()::text
    or exists (
      select 1
      from public.user_sections us
      where us.user_id::text = auth.uid()::text
        and coalesce(us.status, 'active') = 'active'
        and (
          (xml_versions.tenant_id is not null and us.tenant_id = xml_versions.tenant_id)
          or (
            xml_versions.perfil_id is not null
            and us.perfil_id is not null
            and us.perfil_id = xml_versions.perfil_id
          )
        )
    )
  );

-- Cancelaciones: lectura limitada al propio usuario o tenant/perfil asignado.
drop policy if exists invoice_cancellations_scoped_read on public.invoice_cancellations;
create policy invoice_cancellations_scoped_read
  on public.invoice_cancellations
  for select to authenticated
  using (
    user_id::text = auth.uid()::text
    or exists (
      select 1
      from public.user_sections us
      where us.user_id::text = auth.uid()::text
        and coalesce(us.status, 'active') = 'active'
        and (
          (invoice_cancellations.tenant_id is not null and us.tenant_id = invoice_cancellations.tenant_id)
          or (
            invoice_cancellations.perfil_id is not null
            and us.perfil_id is not null
            and us.perfil_id = invoice_cancellations.perfil_id
          )
        )
    )
  );

-- Bloquear escrituras directas de usuarios normales.
drop policy if exists pac_requests_no_client_write on public.pac_requests;
create policy pac_requests_no_client_write
  on public.pac_requests for all to authenticated
  using (false)
  with check (false);

drop policy if exists pac_responses_no_client_write on public.pac_responses;
create policy pac_responses_no_client_write
  on public.pac_responses for all to authenticated
  using (false)
  with check (false);

drop policy if exists xml_versions_no_client_write on public.xml_versions;
create policy xml_versions_no_client_write
  on public.xml_versions for all to authenticated
  using (false)
  with check (false);

drop policy if exists invoice_cancellations_no_client_write on public.invoice_cancellations;
create policy invoice_cancellations_no_client_write
  on public.invoice_cancellations for all to authenticated
  using (false)
  with check (false);
