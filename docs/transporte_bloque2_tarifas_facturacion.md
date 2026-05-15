# Transporte - Bloque 2: tarifas e impuestos configurables

## Objetivo

La factura de servicio ya no debe depender de IVA fijo ni de importes capturados manualmente en el navegador. El cálculo fiscal se hace desde el servidor usando tarifas configuradas por `user_id` y `perfil_id`.

## Flujo implementado

1. En `Catálogos > Tarifas` se configura una tarifa por cliente, ruta, origen, destino, producto y tipo de cálculo.
2. Cada tarifa define si aplica IVA, si aplica retención y sus porcentajes.
3. Al abrir `Facturar servicio`, GE CONTROL carga solo Cartas Porte timbradas y no facturadas.
4. El backend recalcula subtotal, IVA, retención y total con la tarifa aplicable.
5. Si una Carta Porte no tiene tarifa, la factura se bloquea hasta configurarla.
6. Si se mezclan Cartas Porte con tasas distintas de IVA/retención, la factura se bloquea para evitar CFDI incorrecto.

## Tipos de tarifa

- `litros`: tarifa por litro transportado.
- `kilos`: tarifa por kilo.
- `distancia`: tarifa por km.
- `viaje`: tarifa fija por viaje.
- `manual`: fallback interno; no debe usarse como operación normal para facturación.

## Impuestos

La fórmula usada es:

```text
Subtotal del flete
+ IVA configurado
- Retención configurada
= Total a pagar
```

El CFDI de servicio se genera como concepto de servicio de transporte (`78101800`, unidad `E48`). La mercancía transportada sigue viviendo en la Carta Porte, no en el concepto de la factura de servicio.

## Migración requerida

Ejecutar en Supabase:

```text
migrations/transporte_bloque2_tarifas_facturacion_20260514.sql
```

Esta migración agrega retención, tasas, banderas fiscales y detalle de cálculo a `tr_facturas_servicio`, además de observaciones en `tr_tarifas`.
