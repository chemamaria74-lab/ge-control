alter table if exists public.user_facilities
  add column if not exists codigo_postal text not null default '',
  add column if not exists domicilio text not null default '',
  add column if not exists calle text not null default '',
  add column if not exists num_ext text not null default '',
  add column if not exists colonia text not null default '',
  add column if not exists municipio text not null default '',
  add column if not exists estado text not null default '',
  add column if not exists pais text not null default 'México';

create index if not exists idx_user_facilities_scope_cp
  on public.user_facilities(user_id, perfil_id, codigo_postal);
