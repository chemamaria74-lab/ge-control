from supabase_config import get_supabase
from typing import Optional

async def cargar_config_desde_supabase(estacion_id: str) -> Optional[ConfigCliente]:
    """Carga la configuración del cliente desde Supabase."""
    supabase = get_supabase()
    
    try:
        response = supabase.table("clientes").select("*").eq("estacion_id", estacion_id).execute()
        if response.data:
            datos = response.data[0]
            return ConfigCliente(
                estacion_id=datos["estacion_id"],
                nombre=datos["nombre"],
                rfc=datos["rfc"],
                unidad_base=datos["unidad_base"],
                densidad_kg_por_litro=datos["densidad_kg_por_litro"],
            )
    except Exception as e:
        print(f"Error cargando config: {e}")
    
    return None

async def guardar_config_en_supabase(config: ConfigCliente) -> bool:
    """Guarda la configuración en Supabase."""
    supabase = get_supabase()
    
    try:
        supabase.table("clientes").upsert({
            "estacion_id": config.estacion_id,
            "nombre": config.nombre,
            "rfc": config.rfc,
            "unidad_base": config.unidad_base,
            "densidad_kg_por_litro": config.densidad_kg_por_litro,
        }).execute()
        return True
    except Exception as e:
        print(f"Error guardando config: {e}")
        return False
