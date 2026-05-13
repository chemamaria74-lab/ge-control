# Configuracion SW Sapien para pruebas

## Credenciales

No se deben guardar credenciales reales en GitHub.

Configurar en Render o en `.env` local:

```env
SW_ENV=test
SW_USER=tu_usuario_sw
SW_PASSWORD=tu_password_sw
```

El archivo `.env.example` contiene solo placeholders.

## Timbres

La cuenta de pruebas tiene un timbre disponible. No ejecutar timbrados de prueba repetidos sin confirmar, porque cada timbrado exitoso consume saldo.

## CSD de prueba recomendado

Del ZIP `Certificados_Pruebas (1).zip`, se verifico este CSD vigente:

```text
RFC: EKU9003173C9
Razon social: ESCUELA KEMPER URGATE SA DE CV
Sucursal: Sucursal 1
Vigencia: 2023-05-18 a 2027-05-18
Certificado:
Certificados_Pruebas/Personas Morales/EKU9003173C9_20230517223532/CSD_EKU9003173C9_20230517223903/CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer
Llave:
Certificados_Pruebas/Personas Morales/EKU9003173C9_20230517223532/CSD_EKU9003173C9_20230517223903/CSD_Sucursal_1_EKU9003173C9_20230517_223850.key
Password de CSD: usar la contraseña indicada por SW/SAT para el paquete de prueba.
```

En SW Sapien Administrador de Timbres, ir a `Emisores` y cargar el `.cer`, `.key` y password del CSD.

## Configuracion en ZControl

En Transporte > Configuracion:

```text
RFC del contribuyente: EKU9003173C9
Nombre / Razon Social: ESCUELA KEMPER URGATE SA DE CV
Regimen Fiscal: 601
Codigo Postal: usar el codigo postal fiscal del certificado/perfil de prueba que indique el SAT/SW
```

El timbrado JSON de SW usa el RFC del nodo `Emisor` para seleccionar el certificado cargado en SW. Por eso el RFC configurado en ZControl debe coincidir exactamente con el CSD registrado en SW.

## Antes de gastar el timbre

1. Confirmar que el CSD aparece como emisor activo en SW.
2. Confirmar que `SW_ENV=test`.
3. Confirmar que ZControl usa el mismo RFC del CSD.
4. Crear un viaje simple.
5. Timbrar una sola Carta Porte o una sola factura de servicio.
