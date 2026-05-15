# Transporte - Bloque 3: operador, quincenas y liquidaciones

## Objetivo

Extender Transporte sin rehacer la parte fiscal. El viaje sigue siendo el eje operativo y la oficina conserva el control. El operador solo recibe una pantalla simple con acciones mínimas.

## Portal operador

El operador entra con un link generado por oficina. Puede ver sus viajes activos y:

- Ver/descargar Carta Porte PDF si ya está timbrada.
- Marcar `Ya lo recibí`.
- Marcar `Voy en camino`.
- Marcar `Ya entregué`.
- Reportar `Tengo problema` con una nota breve.

Cuando reporta problema, GE CONTROL registra:

- evento en timeline del viaje,
- notificación interna pendiente para oficina.

WhatsApp queda solo como canal futuro de aviso; no almacena documentos ni estado operativo.

## Liquidaciones / quincenas

La oficina puede generar liquidaciones por chofer en:

- primera quincena (`YYYY-MM-Q1`),
- segunda quincena (`YYYY-MM-Q2`),
- mes completo (`YYYY-MM`).

La liquidación toma viajes pendientes del periodo, calcula tarifa desde `tr_tarifas`, suma gastos aprobados y permite:

- anticipos,
- comisión extra,
- descuentos,
- notas,
- método de pago: efectivo, transferencia, cheque u otro,
- referencia de pago.

Al pagar una liquidación:

- cambia a `pagada`,
- guarda `paid_at`,
- guarda método y referencia,
- marca los viajes como `liquidacion_status = pagada`,
- agrega evento en cada viaje.

## Export

Cada liquidación se puede exportar a Excel (`.xlsx`) con:

- encabezado,
- chofer,
- periodo,
- partidas por viaje,
- subtotal,
- IVA,
- retención,
- gastos,
- comisión,
- descuentos,
- anticipos,
- total a pagar.

## Migración requerida

Ejecutar en Supabase:

```text
migrations/transporte_bloque3_operador_liquidaciones_20260514.sql
```
