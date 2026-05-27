# Fase 5 - Transporte: cierre local

Estado: Cerrada local en riesgos criticos / pendiente UI rica.

Fecha de corte: 2026-05-26.

## Mejoras relevantes

- Link de operador valida que el chofer pertenezca al perfil activo.
- Tokens previos del mismo chofer/perfil se reemplazan al generar un nuevo link.
- Portal operador queda limitado por `chofer_id` y `perfil_id`.
- Carta Porte PDF/XML bloquea entrega de PDF si el XML no valida como Carta Porte de carretera.
- Timbrado de petroliferos sigue bloqueado correctamente hasta cerrar Hidrocarburos con SW Sapien.

## Estado funcional local

- Dashboard Transporte: conectado.
- Clientes: conectado.
- Operadores / choferes: conectado.
- Unidades: conectado.
- Viajes: conectado.
- Facturas de servicio: conectado.
- PDF/XML Carta Porte: conectado con validacion bloqueante.
- Portal operador: conectado y acotado por chofer/perfil.
- Liquidaciones: conectado.
- Catalogos avanzados: existen con CRUD generico.

## Pendiente

- UI rica para remolques, permisos, seguros y vinculacion a vehiculos.
- Prueba real con Supabase.
- Fixtures faltantes para `tests/test_cfdi_xml_analyzer.py`.
- Validar flujo completo viaje -> timbrado sandbox -> PDF/XML -> operador.

## Riesgos residuales

- Los catalogos avanzados pueden estar vacios en Supabase aunque ya existan tablas/endpoints.
- Carta Porte puede depender de datos incompletos de vehiculo, seguro, permiso o producto.
- Hidrocarburos/Petroliferos debe cerrarse con SW Sapien antes de desbloquear timbrado de Magna, Premium y Diesel.

## Verificacion local realizada

- `python3 -m compileall routes/transporte.py`: OK.
- Import con `uv run` y variables dummy de Supabase: OK.
- Builder CFDI/Carta Porte 3.1 con datos completos de prueba: OK.
- Revisión simple de botones `onclick` en pantallas Transporte/Operador: sin funciones faltantes.

## Bloqueos para cierre productivo

- No hay credenciales Supabase reales cargadas en esta sesion para prueba contra datos vivos.
- `tests/test_cfdi_xml_analyzer.py` falla porque faltan XML fixtures en `tests/fixtures/xml`.
- Falta prueba sandbox real con SW Sapien para el flujo completo fiscal-operativo.
