# Evidencia Gas LP / HidroYPetro - 2026-06-02

## Hallazgo de clave SAT

- Catalogo publico Anexo 20 consultado:
  - `15111510`: Gas licuado de petroleo / Gas LP.
  - `15101515`: Gasolina premium mayor o igual a 91 octanos.
- Fuentes:
  - https://www.gncys.com/anexo20/4.0/claveprodserv/15111510
  - https://www.gncys.com/anexo20/4.0/guia-factura-global-apendice-3.aspx
- Por semantica fiscal del producto real de GAS LUX, la clave canonica de Gas LP debe permanecer como `15111510`.
- `15101515` queda solo como variante diagnostica SW HyP, no como configuracion definitiva del negocio.

## XML historicos timbrados por otro PAC

Archivos comparados:

- `/Users/majooomejia/Downloads/FACTURA PUBLICO GRAL.xml`
- `/Users/majooomejia/Downloads/FACTURA CLIENTE.xml`

Datos comunes:

- Emisor: `GLU760309457` - `GAS LUX`
- PAC: `MAS0810247C0`
- CFDI version: `4.0`
- Concepto:
  - `ClaveProdServ="15111510"`
  - `ClaveUnidad="LTR"`
  - `Descripcion="LITRO DE GAS LP"`
  - Sin `ComplementoConcepto/HidroYPetro`

Factura publico general:

- Receptor: `XAXX010101000`
- UUID: `239BFDF4-80EB-4C63-9CF1-83487FD327A5`
- No contiene `cfdi:InformacionGlobal`
- Fue timbrada por el PAC historico.

Factura cliente:

- Receptor: `SAHL750526ML8`
- UUID: `EB1BB969-7F52-4D59-8250-0CAE6A0B49FC`
- Fue timbrada por el PAC historico.

## Diagnostico SW/Forsedi HyP

Matriz L_CNE ejecutada en produccion con:

- Usuario interno: Anabel
- Empresa/RFC: `GAS LUX` / `GLU760309457`
- Endpoint diagnostico: `POST /api/internal-auth/gas-lp/hyp-l-cne-diagnostics`
- Modo: `diagnostic=true`, `persisted=false`
- XML completo y respuestas: `/private/tmp/gas_lp_hyp_lcne_matrix_results.json`

Resultado:

- Todas las pruebas incluyeron `ComplementoConcepto/HidroYPetro`.
- Ningun XML contenia `15111510` cuando se probo la variante SW `15101515`.
- Todas las combinaciones de permiso/tipo/clave fallaron con `CCHYP107`.

Respuesta PAC/SW repetida:

```text
CCHYP107 - El valor registrado en NumeroPermiso no se encuentra en la lista L_CNE o no corresponde con la nomenclatura del numero de permiso asociada a la clave registrada en la columna "Nomenclatura del numero de permiso" conforme al catalogo c_TipoPermiso.
```

Conclusion tecnica:

- El rechazo actual no se resolvio con `15101515`.
- El rechazo tampoco se resolvio transformando permisos `LP/...` a `PL/...` o `CNE/PL/...`.
- El punto bloqueante parece ser el cruce privado L_CNE:

```text
RFC GLU760309457 + NumeroPermiso + ClaveHYP
```

- No consolidar `15101515` como clave definitiva del sistema.
- No modificar permisos reales en BD.
- No quitar HyP para SW mientras el PAC lo exija.
