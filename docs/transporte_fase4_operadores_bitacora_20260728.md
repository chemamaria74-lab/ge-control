# Transporte — Fase 4: Operadores en ruta y bitácora

Fecha: 28 de julio de 2026

## Alcance implementado

- El tablero **Operadores en ruta** carga al entrar, conserva actualización manual y se refresca cada 60 segundos mientras permanece visible.
- El portal permite iniciar una **prebitácora de recorrido vacío** antes de contar con factura o Carta Porte.
- Estados del tramo previo:
  - `SIN_INICIAR`
  - `EN_RUTA_VACIO`
  - `EN_TERMINAL`
- El operador puede registrar una incidencia durante el recorrido vacío.
- Al crear el viaje desde la factura, los eventos del tramo vacío se transfieren a la bitácora definitiva.
- El traslado con carga inicia con un evento explícito `LLEGADA_CARGA`.
- La prebitácora no se borra antes de tiempo: en el flujo combinado se limpia solamente después de que el timbrado termina correctamente.
- Administración puede ver en el tablero a operadores que todavía se encuentran en recorrido vacío.
- Cada evento con ubicación ofrece enlace directo al punto en mapa y muestra la precisión disponible.
- La historia visible aumentó de 6 a 10 eventos.
- El aviso de uso de ubicación se presenta una sola vez por versión y guarda fecha de aceptación.
- La desactivación del acceso y la sesión única continúan siendo aplicadas por el esquema de autenticación formal de la fase 1.

## Persistencia diferida

La migración diferida agrega `pretrip_json` a `tr_operador_accesos`, junto con las columnas de aceptación del aviso. No debe aplicarse hasta completar y aprobar las fases 1–7.

## Aislamiento

- La prebitácora está ligada a un acceso que contiene `user_id`, `perfil_id` y `chofer_id`.
- El tablero administrativo filtra tanto viajes como accesos por el usuario y la empresa activa.
- No se modificó Gas LP.

## Validación local

- Sintaxis de Python y JavaScript aprobada.
- 48 pruebas focales aprobadas.
- Sin conexiones ni pruebas reales contra producción.
- Sin migraciones aplicadas.
- Sin `push` ni despliegue.
