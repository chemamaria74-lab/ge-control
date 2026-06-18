-- Correccion de alcance:
-- 1. Revierte los campos Gas LP que fueron tocados por error por el seed anterior.
-- 2. Registra las cuatro instalaciones en Transporte v2 como origenes,
--    ligadas a los clientes existentes mediante RFC, sin duplicar registros.

begin;

-- Restaurar datos operativos Gas LP desde la evidencia previa al seed:
-- import_payload original + ubicaciones usadas en XML timbrados.
update public.user_facilities uf
set
  descripcion = coalesce(nullif(uf.import_payload ->> 'descripcion', ''), uf.descripcion),
  domicilio = src.direccion,
  calle = src.direccion,
  codigo_postal = src.cp,
  municipio = src.municipio,
  estado = src.estado,
  pais = 'México'
from (
  values
    (2::bigint, 'Carr Federal Num 54 Tramo Morelos a Concepción del Oro Zac', '98470', 'Villa de Cos', 'Zacatecas'),
    (3::bigint, 'Carr Teocaltiche - Villa Hidalgo Km 19, Tepusco, Villa Hidalgo, Jalisco', '47260', 'Villa Hidalgo', 'Jalisco'),
    (4::bigint, 'Carretera Jerez-Zacatecas, Km 2, Municipio de Jerez de García Salinas, Jerez, Zacatecas', '99300', 'Jerez de García Salinas', 'Zacatecas'),
    (5::bigint, 'Carretera a Zacatecas Km 3, Tlaltenango de Sanchez Roman, Zacatecas', '99700', 'Tlaltenango de Sanchez Roman', 'Zacatecas')
) as src(facility_id, direccion, cp, municipio, estado)
where uf.id = src.facility_id
  and uf.import_source = 'excel_gas_lp_facilities';

update public.gas_lp_facility_carta_porte_config cfg
set
  tipo_ubicacion = src.tipo,
  id_ubicacion_carta_porte = src.id_ubicacion,
  estado_sat = src.estado_sat,
  municipio_sat = src.municipio_sat,
  localidad_sat = src.localidad_sat,
  referencia_carta_porte = src.referencia,
  metadata_json = '{}'::jsonb,
  updated_at = now()
from (
  values
    (2::bigint, 'origen', 'OR000001', 'ZAC', '',    '',   'Carr Federal Num 54 Tramo Morelos a Concepción del Oro Zac'),
    (3::bigint, 'origen', 'OR000001', 'JAL', '116', '',   'Carr Teocaltiche - Villa Hidalgo Km 19, Tepusco, Villa Hidalgo, Jalisco'),
    (4::bigint, 'origen', 'OR000004', 'ZAC', '020', '02', 'Carretera Jerez-Zacatecas, Km 2, Municipio de Jerez de García Salinas, Jerez, Zacatecas'),
    (5::bigint, 'origen', 'OR000005', 'ZAC', '048', '',   'Carretera a Zacatecas Km 3, Tlaltenango de Sanchez Roman, Zacatecas')
) as src(facility_id, tipo, id_ubicacion, estado_sat, municipio_sat, localidad_sat, referencia)
where cfg.facility_id = src.facility_id
  and cfg.metadata_json ->> 'source' = 'gas_lp_initial_transport_clients_facilities_20260618';

do $$
declare
  rec record;
  cliente record;
  origen_id bigint;
begin
  for rec in
    select *
    from (
      values
        (
          'GLU760309457',
          'Planta Jerez',
          'Carretera Jerez-Zacatecas, Km 2, Municipio de Jerez de García Salinas, Jerez, Zacatecas',
          '99300',
          'Zacatecas',
          'Jerez de García Salinas',
          'OR000004',
          'ZAC',
          '020',
          '02'
        ),
        (
          'DGC881020LC4',
          'Planta Tlaltenango',
          'Carretera a Zacatecas Km 3, Tlaltenango de Sánchez Román, Zacatecas',
          '99700',
          'Zacatecas',
          'Tlaltenango de Sánchez Román',
          'OR000005',
          'ZAC',
          '048',
          ''
        ),
        (
          'AGA9603186X8',
          'Planta Alfa Tepusco',
          'Carr Teocaltiche - Villa Hidalgo Km 19, Tepusco, Villa Hidalgo, Jalisco',
          '47260',
          'Jalisco',
          'Villa Hidalgo',
          'OR000001',
          'JAL',
          '116',
          ''
        ),
        (
          'AGA990907II8',
          'Planta Villa de Cos Aure',
          'Carr Federal Num 54 Tramo Morelos a Concepción del Oro, Zac.',
          '98470',
          'Zacatecas',
          'Villa de Cos',
          'OR000001',
          'ZAC',
          '051',
          '10'
        )
    ) as seed(
      rfc,
      nombre,
      direccion,
      cp,
      estado,
      ciudad,
      id_ubicacion,
      estado_sat,
      municipio_sat,
      localidad_sat
    )
  loop
    select c.*
      into cliente
    from public.tr_clientes c
    where c.perfil_id = 410
      and c.activo is distinct from false
      and upper(c.rfc) = rec.rfc
    order by c.id
    limit 1;

    if cliente.id is null then
      raise exception 'No se encontró cliente Transporte v2 para RFC %', rec.rfc;
    end if;

    select o.id
      into origen_id
    from public.tr_origenes o
    where o.user_id = cliente.user_id
      and o.perfil_id = cliente.perfil_id
      and (
        o.cliente_id = cliente.id
        or (
          upper(o.rfc) = rec.rfc
          and upper(o.nombre) = upper(rec.nombre)
        )
      )
    order by o.id
    limit 1;

    if origen_id is null then
      insert into public.tr_origenes (
        user_id,
        perfil_id,
        nombre,
        rfc,
        cp,
        codigo_postal,
        direccion,
        ciudad,
        estado,
        pais,
        tipo,
        tipo_carta_porte,
        cliente_id,
        cliente_nombre,
        clave_instalacion,
        id_ubicacion_carta_porte,
        estado_sat,
        municipio_sat,
        localidad_sat,
        activo,
        metadata,
        created_at,
        updated_at
      )
      values (
        cliente.user_id,
        cliente.perfil_id,
        rec.nombre,
        cliente.rfc,
        rec.cp,
        rec.cp,
        rec.direccion,
        rec.ciudad,
        rec.estado,
        'México',
        'cliente',
        'Origen',
        cliente.id,
        cliente.nombre,
        '',
        rec.id_ubicacion,
        rec.estado_sat,
        rec.municipio_sat,
        rec.localidad_sat,
        true,
        jsonb_build_object(
          'source', 'transporte_v2_client_origin_facilities_20260618',
          'tipo_carta_porte', 'Origen',
          'cliente_id', cliente.id,
          'cliente_nombre', cliente.nombre,
          'id_ubicacion_carta_porte', rec.id_ubicacion,
          'estado_sat', rec.estado_sat,
          'municipio_sat', rec.municipio_sat,
          'localidad_sat', rec.localidad_sat,
          'referencia', rec.direccion
        ),
        now(),
        now()
      );
    else
      update public.tr_origenes
      set
        nombre = rec.nombre,
        rfc = cliente.rfc,
        cp = rec.cp,
        codigo_postal = rec.cp,
        direccion = rec.direccion,
        ciudad = rec.ciudad,
        estado = rec.estado,
        pais = 'México',
        tipo = 'cliente',
        tipo_carta_porte = 'Origen',
        cliente_id = cliente.id,
        cliente_nombre = cliente.nombre,
        id_ubicacion_carta_porte = rec.id_ubicacion,
        estado_sat = rec.estado_sat,
        municipio_sat = rec.municipio_sat,
        localidad_sat = rec.localidad_sat,
        activo = true,
        metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
          'source', 'transporte_v2_client_origin_facilities_20260618',
          'tipo_carta_porte', 'Origen',
          'cliente_id', cliente.id,
          'cliente_nombre', cliente.nombre,
          'id_ubicacion_carta_porte', rec.id_ubicacion,
          'estado_sat', rec.estado_sat,
          'municipio_sat', rec.municipio_sat,
          'localidad_sat', rec.localidad_sat,
          'referencia', rec.direccion
        ),
        updated_at = now()
      where id = origen_id;
    end if;
  end loop;
end $$;

commit;
