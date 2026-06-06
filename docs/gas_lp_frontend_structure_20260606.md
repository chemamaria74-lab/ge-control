# Estructura local Gas LP y Admin

Este documento resume la estructura creada para evitar templates monolíticos y facilitar diagnóstico por módulo.

## Templates principales

- `templates/app.html`: shell principal del dashboard Gas LP.
- `templates/asistente_gas_lp.html`: shell del asistente Gas LP.
- `templates/conciliacion_gas_lp.html`: shell de conciliación Gas LP.
- `templates/admin_saas.html`: shell de administración SaaS.

Los shells cargan CSS/JS externos y componen HTML con comentarios `<!-- ge-include: ... -->`.

## Parciales HTML

- `templates/app/`
  - `_body.html`
  - `_critical_modal.html`
  - `_confirm_modal.html`
- `templates/gas_lp/asistente/`
  - `_dashboard.html`
  - `_facturacion.html`
  - `_facturas.html`
  - `_clientes.html`
  - `_carta_porte.html`
  - `_modals.html`
- `templates/gas_lp/conciliacion/`
  - `_header_kpis_tabs.html`
  - `_facturas.html`
  - `_publico.html`
  - `_complementos.html`
  - `_credito.html`
  - `_sat.html`
  - `_modals.html`
- `templates/admin_saas/`
  - `_login.html`
  - `_topbar.html`
  - `_dashboard.html`
  - `_clientes.html`
  - `_empresas.html`
  - `_usuarios.html`
  - `_suscripciones.html`
  - `_facturacion_ge.html`
  - `_administracion.html`
  - `_modulos.html`
  - `_reparacion.html`
  - `_auditoria.html`

## Assets

- `static/css/gas_lp/asistente.css`
- `static/css/app.css`
- `static/css/gas_lp/conciliacion.css`
- `static/css/admin_saas.css`
- `static/js/app/*.js`
- `static/js/gas_lp/asistente/*.js`
- `static/js/gas_lp/conciliacion/*.js`
- `static/js/admin_saas/*.js`

Los scripts mantienen orden numérico para cargar estado, utilidades, módulos de negocio e inicialización.

En `static/js/app/` el dashboard principal queda dividido en:

- `00_i18n.js`
- `10_state_helpers.js`
- `20_auth_transport.js`
- `30_company_settings.js`
- `40_facilities_navigation.js`
- `50_analytics_upload.js`
- `60_carta_porte_processing_history.js`
- `70_admin_catalogs_users.js`
- `80_advanced_autoconsumo_forecast.js`
- `90_init.js`
- `90_onboarding.js`

## Contrato de descuentos

El precio por litro se captura con IVA. Los descuentos tienen contratos distintos:

- `Descuento por litro`: monto con IVA por litro.
- `Descuento total en pesos`: monto base antes de IVA a restar del subtotal.

Para el XML CFDI, el descuento por litro se convierte a base antes de IVA. El descuento total ya se captura como base antes de IVA.

## Validación local

Ejecutar:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ge_pycache python3 scripts/validate_frontend_refactor.py
```

La validación revisa:

- sintaxis de JS modularizado,
- compilación de `main.py`,
- expansión de includes de los templates clave,
- ausencia de `<style>`/`<script>` inline en los shells principales.
