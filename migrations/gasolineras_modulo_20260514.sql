-- Z Control - Modulo Gasolineras MX
-- Ejecutar en Supabase SQL Editor.
-- Este modulo queda separado de Gas LP y Transporte por prefijo gaso_,
-- user_id, perfil_id y datos operativos propios.

alter table public.user_sections
drop constraint if exists user_sections_section_check;

alter table public.user_sections
add constraint user_sections_section_check
check (section in ('gas_lp', 'transporte', 'gasolineras'));

create table if not exists public.gaso_settings (
  id          bigserial primary key,
  user_id     text not null,
  perfil_id   bigint,
  data        jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create unique index if not exists idx_gaso_settings_user_perfil
  on public.gaso_settings (user_id, perfil_id);

create table if not exists public.gaso_estaciones (
  id                      bigserial primary key,
  user_id                  text not null,
  perfil_id                bigint,
  nombre                   text not null default '',
  permiso_cre              text not null default '',
  permiso_cne              text not null default '',
  marca                    text not null default '',
  estado                   text not null default '',
  municipio                text not null default '',
  direccion                text not null default '',
  lat                      numeric,
  lng                      numeric,
  precio_regular           numeric not null default 0,
  precio_premium           numeric not null default 0,
  precio_diesel            numeric not null default 0,
  volumen_mensual_litros   numeric not null default 0,
  costo_regular            numeric not null default 0,
  costo_premium            numeric not null default 0,
  costo_diesel             numeric not null default 0,
  opex_mensual             numeric not null default 0,
  cne_status               text not null default 'vigente',
  propia                   boolean not null default true,
  activa                   boolean not null default true,
  data                     jsonb not null default '{}'::jsonb,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  constraint gaso_estaciones_coord_mx check (
    lat is null or lng is null or (lat between 14 and 32 and lng between -118 and -87)
  )
);

create index if not exists idx_gaso_estaciones_user_perfil
  on public.gaso_estaciones (user_id, perfil_id);

create index if not exists idx_gaso_estaciones_geo
  on public.gaso_estaciones (lat, lng);

create table if not exists public.gaso_market_stations (
  id              bigserial primary key,
  permiso_cre      text not null default '',
  permiso_cne      text not null default '',
  nombre           text not null default '',
  marca            text not null default '',
  estado           text not null default '',
  municipio        text not null default '',
  direccion        text not null default '',
  lat              numeric,
  lng              numeric,
  precio_regular   numeric not null default 0,
  precio_premium   numeric not null default 0,
  precio_diesel    numeric not null default 0,
  cne_status       text not null default 'vigente',
  fuente           text not null default 'CRE_ESTACIONES',
  activa           boolean not null default true,
  data             jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint gaso_market_coord_mx check (
    lat is null or lng is null or (lat between 14 and 32 and lng between -118 and -87)
  )
);

create index if not exists idx_gaso_market_geo
  on public.gaso_market_stations (lat, lng);

create index if not exists idx_gaso_market_permiso
  on public.gaso_market_stations (permiso_cre);

create table if not exists public.gaso_precio_historico (
  id                bigserial primary key,
  user_id            text not null,
  perfil_id          bigint,
  estacion_id        bigint references public.gaso_estaciones(id) on delete cascade,
  market_station_id  bigint references public.gaso_market_stations(id) on delete cascade,
  producto           text not null check (producto in ('regular', 'premium', 'diesel')),
  precio             numeric not null,
  timestamp          timestamptz not null default now(),
  fuente             text not null default 'CLIENTE_MANUAL',
  delta_anterior     numeric not null default 0,
  data               jsonb not null default '{}'::jsonb
);

create index if not exists idx_gaso_precio_hist_user_perfil
  on public.gaso_precio_historico (user_id, perfil_id, producto, timestamp desc);

create index if not exists idx_gaso_precio_hist_estacion
  on public.gaso_precio_historico (estacion_id, producto, timestamp desc);

create table if not exists public.gaso_cfdi (
  id            bigserial primary key,
  user_id        text not null,
  perfil_id      bigint,
  estacion_id    bigint references public.gaso_estaciones(id) on delete set null,
  uuid_sat       text not null default '',
  xml_content    text not null default '',
  pdf_path       text not null default '',
  status         text not null default 'vigente',
  created_at     timestamptz not null default now()
);

create index if not exists idx_gaso_cfdi_user_perfil
  on public.gaso_cfdi (user_id, perfil_id);

create table if not exists public.gaso_cfdi_compras (
  id                  bigserial primary key,
  user_id              text not null,
  perfil_id            bigint,
  estacion_id          bigint references public.gaso_estaciones(id) on delete set null,
  uuid_sat             text not null default '',
  rfc_emisor           text not null default '',
  rfc_receptor         text not null default '',
  fecha                timestamptz,
  litros               numeric not null default 0,
  importe              numeric not null default 0,
  costo_real_litro     numeric not null default 0,
  xml_content          text not null default '',
  data                 jsonb not null default '{}'::jsonb,
  created_at           timestamptz not null default now()
);

create index if not exists idx_gaso_cfdi_compras_user_perfil
  on public.gaso_cfdi_compras (user_id, perfil_id, fecha desc);

create table if not exists public.gaso_ventas (
  id                  bigserial primary key,
  user_id              text not null,
  perfil_id            bigint,
  estacion_id          bigint references public.gaso_estaciones(id) on delete set null,
  fecha                date,
  producto             text not null default 'regular' check (producto in ('regular', 'premium', 'diesel')),
  litros_vendidos      numeric not null default 0,
  transacciones        integer not null default 0,
  turno                text not null default '',
  precio_venta         numeric not null default 0,
  dispensario          text not null default '',
  data                 jsonb not null default '{}'::jsonb,
  created_at           timestamptz not null default now()
);

create index if not exists idx_gaso_ventas_user_perfil
  on public.gaso_ventas (user_id, perfil_id, fecha desc);

create table if not exists public.gaso_alertas (
  id              bigserial primary key,
  user_id          text not null,
  perfil_id        bigint,
  estacion_id      bigint references public.gaso_estaciones(id) on delete cascade,
  tipo             text not null,
  severidad        text not null default 'media',
  mensaje          text not null,
  status           text not null default 'abierta',
  data             jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now(),
  closed_at        timestamptz
);

create index if not exists idx_gaso_alertas_user_perfil
  on public.gaso_alertas (user_id, perfil_id, status, created_at desc);

create table if not exists public.gaso_brand_benchmarks (
  id              bigserial primary key,
  marca           text not null,
  region          text not null default 'nacional',
  producto        text not null check (producto in ('regular', 'premium', 'diesel')),
  tar_estimado     numeric not null default 0,
  margen_tipico    numeric not null default 0,
  cobertura        text not null default '',
  fuente           text not null default 'PROFECO_TAR',
  data             jsonb not null default '{}'::jsonb,
  updated_at       timestamptz not null default now()
);

create unique index if not exists idx_gaso_brand_benchmarks_unique
  on public.gaso_brand_benchmarks (marca, region, producto);

-- Para habilitar un usuario:
-- insert into public.user_sections (user_id, section, role, status, display_name)
-- values ('UUID_DEL_USUARIO', 'gasolineras', 'user', 'active', 'Nombre')
-- on conflict (user_id, section) do update set status = 'active';
