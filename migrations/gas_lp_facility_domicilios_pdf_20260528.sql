alter table if exists public.user_facilities
  add column if not exists domicilio_operativo text not null default '',
  add column if not exists codigo_postal text not null default '';

