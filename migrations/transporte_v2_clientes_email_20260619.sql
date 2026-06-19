-- GE Control - Transporte v2 clientes email.
-- Permite guardar correo de facturacion desde Catalogos > Clientes.

alter table if exists public.tr_clientes
  add column if not exists metadata jsonb not null default '{}'::jsonb,
  add column if not exists email text not null default '',
  add column if not exists email_facturacion text not null default '';

create index if not exists idx_tr_clientes_email_facturacion
  on public.tr_clientes(user_id, perfil_id, email_facturacion)
  where email_facturacion <> '';

comment on column public.tr_clientes.email_facturacion is
  'Correo principal para facturacion y envio de documentos del cliente Transporte.';
