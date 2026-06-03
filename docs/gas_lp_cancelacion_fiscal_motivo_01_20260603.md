# Prueba exitosa: cancelacion fiscal Gas LP motivo 01

Fecha: 2026-06-03

## Caso

- Modulo: Conciliacion Gas LP
- Empresa emisora: AURE GAS
- RFC emisor: AGA990907II8
- Cliente: J JESUS ROBLES NAVA
- UUID cancelado: 6d09da66-366b-41f0-b778-0b89ed625b5f
- Total factura incorrecta: 4990.50
- Motivo SAT: 01 - Comprobante emitido con errores con relacion
- UUID sustituto: aa054375-5a74-44c3-ad8c-e2e1070512c4

## Validaciones previas

- El RFC emisor se tomo del XML original de la factura, no del perfil seleccionado.
- El endpoint final esperado uso AGA990907II8:
  `https://services.sw.com.mx/cfdi33/cancel/AGA990907II8/6d09da66-366b-41f0-b778-0b89ed625b5f/01/aa054375-5a74-44c3-ad8c-e2e1070512c4`
- El estado previo no iniciaba con `cancel`.
- Se valido que el UUID sustituto estuviera informado para motivo 01.

## Resultado SW/SAT/PAC

- SW/SAT/PAC recibio la solicitud satisfactoriamente.
- Se genero acuse XML.
- `CodEstatus`: Comprobante recibido satisfactoriamente.
- `EstatusUUID`: 201.
- El estado fiscal de la factura incorrecta quedo como `Cancelada fiscalmente`.

## Evidencia conservada

- Respuesta SW completa en metadata fiscal.
- Acuse XML en metadata fiscal.
- Endpoint final usado en metadata fiscal, sin secretos.
- RFC emisor usado en metadata fiscal.

## Alcance no afectado

Esta prueba no requirio modificar ni regenerar:

- XML timbrado original
- PDF
- Timbrado normal
- Calculos
- Correo
- Complemento HyP

## Nota operativa

No reenviar cancelacion fiscal para el UUID `6d09da66-366b-41f0-b778-0b89ed625b5f`.
