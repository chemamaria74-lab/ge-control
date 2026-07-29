# Transporte — Fase 6: onboarding, suscripción y conservación

Fecha: 28 de julio de 2026

## Resumen implementado

- Nueva vista **Administración → Suscripción y alta**.
- Medición mensual por empresa activa de CFDI con UUID vigente.
- Presenta:
  - nombre del plan;
  - timbres incluidos al mes;
  - timbres usados;
  - timbres disponibles;
  - estado del checklist de alta.
- La medición no bloquea timbrados por defecto (`meter_only`).
- Sólo debe usarse `hard_limit` cuando el contrato defina expresamente el bloqueo al agotar timbres.
- La configuración comercial se lee desde `subscriptions.limits_json.transporte`.

## Campos del plan Transporte

```json
{
  "transporte": {
    "enabled": true,
    "companies": 1,
    "operators": 5,
    "vehicles": null,
    "timbres_included_monthly": 100,
    "stamp_enforcement": "meter_only",
    "retention_days": 365,
    "can_stamp_carta_porte": true,
    "can_invoice_service": true,
    "can_use_liquidaciones": true
  }
}
```

`null` significa que el límite debe definirse por contrato o no está limitado automáticamente.

## Información indispensable para dar de alta un cliente

GE Control debe obtener y validar:

1. Razón social y RFC.
2. Constancia de Situación Fiscal vigente.
3. Domicilio y código postal fiscal.
4. Régimen fiscal.
5. Nombre, correo y teléfono del administrador responsable.
6. Contrato aceptado y plan contratado.
7. Número de empresas incluidas.
8. Timbres mensuales incluidos y política de excedentes.
9. Módulos y funciones habilitados.
10. Vigencia, renovación y condiciones de suspensión.

Después de activar la empresa, el administrador del cliente completa:

1. Permiso CRE del transportista.
2. Clientes y proveedores.
3. Instalaciones con permiso CRE.
4. Productos.
5. Operadores.
6. Vehículos y remolques.
7. Rutas y tarifas.
8. Usuarios de operador.
9. Configuración de Nómina.
10. Logo y diseño de documentos.

## Conservación y bajas

- Revocar un acceso ya no elimina físicamente la credencial.
- La revocación invalida inmediatamente la sesión.
- Viajes, documentos, pagos y bitácoras mantienen su relación con el operador.
- La conservación mínima configurada es de 365 días.
- No se incorporó una tarea destructiva de purga automática.
- Cualquier eliminación posterior al periodo debe contemplar obligaciones fiscales, laborales, contractuales y de litigio; no debe ejecutarse sólo por antigüedad.

## Elementos recomendados para contrato

- alcance del módulo y empresas habilitadas;
- usuarios administrativos y operadores incluidos;
- timbres incluidos, excedentes y reembolsos;
- disponibilidad y soporte;
- responsabilidades sobre datos fiscales y permisos;
- tratamiento de geolocalización;
- conservación, exportación y devolución de información;
- suspensión por falta de pago o uso indebido;
- propiedad intelectual;
- limitación de responsabilidad;
- terminación y plazo para descargar información.

El texto definitivo debe revisarse con asesoría jurídica mexicana antes de firma.

## Validación local

- Sintaxis Python y JavaScript aprobada.
- 51 pruebas focales aprobadas antes de la corrida completa.
- Sin pruebas reales, migraciones, `push` ni despliegue.
- Sin modificaciones funcionales en Gas LP.
