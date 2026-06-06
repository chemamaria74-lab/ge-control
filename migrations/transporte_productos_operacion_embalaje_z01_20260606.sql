-- Ajusta el embalaje default de productos operativos transportados.
-- Para combustibles/hidrocarburos a granel en autotanque/cisterna se usa Z01
-- como valor operativo por defecto; 4H2 corresponde a cajas de plastico rigido.

alter table if exists public.tr_productos_operacion
  alter column embalaje set default 'Z01';

update public.tr_productos_operacion
   set embalaje = 'Z01',
       updated_at = now()
 where upper(coalesce(embalaje, '')) = '4H2';
