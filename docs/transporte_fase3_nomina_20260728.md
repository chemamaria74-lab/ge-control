# Transporte — Fase 3: simplificación de Nómina

Fecha: 28 de julio de 2026

## Alcance implementado

- La navegación principal de Nómina queda en tres vistas: **Por pagar**, **Pagados** y **Configuración**.
- **Configuración** agrupa las tarifas por viaje y las bases de nómina.
- La periodicidad configurada por la empresa (semanal, quincenal o mensual) es la única base editable que se muestra.
- **Por pagar** carga automáticamente los viajes pendientes de los últimos 12 meses.
- El resumen muestra la fecha del pendiente más antiguo y su antigüedad en días.
- Los viajes ya pagados dejaron de mezclarse con los pendientes.
- **Pagados** usa filtros propios de fecha y operador, consulta 60 días por defecto y devuelve como máximo 100 registros por búsqueda.
- El historial admite búsquedas de hasta un año.
- La consulta de pendientes se pagina para no truncarse en 1,000 viajes. Si el rango supera 20,000 viajes, exige acotarlo por fecha u operador en vez de presentar un total incompleto.

## Seguridad y aislamiento

- Todas las consultas conservan el aislamiento por `user_id` y `perfil_id`.
- Los catálogos de operadores, rutas, clientes, tarifas, liquidaciones e items continúan filtrados por la empresa activa.
- No se modificó ningún archivo del módulo Gas LP.

## Validación local

- Sintaxis JavaScript validada.
- 44 pruebas focales de Transporte, flujo de operador, aislamiento y Nómina aprobadas.
- No se ejecutaron pruebas reales contra producción.
- No se aplicaron migraciones.
- No se hizo `push` ni despliegue.

## Pendiente para la liberación final

- Validación visual en un ambiente local o de staging con datos representativos.
- Aplicar las migraciones acumuladas solamente después de completar la fase 7 y aprobar el plan de despliegue.
- Ejecutar respaldo y lista de comprobación antes de liberar a producción.
