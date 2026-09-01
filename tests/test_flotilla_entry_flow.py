import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-placeholder-key")

from main import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_flotilla_role_always_requires_its_own_login():
    response = client.get("/modulo/gas-lp/roles")

    assert response.status_code == 200
    assert 'href="/gas-lp/flotilla/acceso?lang=es"' in response.text


def test_transport_expenses_login_identifies_the_requested_portal():
    expenses = client.get("/transporte-v2/login-admin?next=/transporte-v2/gastos")
    admin = client.get("/transporte-v2/login-admin?next=/transporte-v2/admin")

    assert expenses.status_code == 200
    assert "Gastos y pagos de Transporte" in expenses.text
    assert "Acceso al control de gastos y pagos" in expenses.text
    assert "Administrador Transporte" in admin.text


def test_flotilla_dashboard_is_hidden_until_session_validation():
    response = client.get("/gas-lp/flotilla")

    assert response.status_code == 200
    assert '<html lang="es" class="fleet-auth-pending">' in response.text
    assert 'id="fleetAuthGate"' in response.text
    assert '/static/css/gas_lp/flotilla_auth_gate.css?v=20260724b' in response.text


def test_flotilla_has_a_dedicated_branded_login():
    response = client.get("/gas-lp/flotilla/acceso")

    assert response.status_code == 200
    assert '<h1>Portal de Gerentes</h1>' in response.text
    assert "Flotilla o a Vales y gastos" in response.text
    assert '<span></span> Gas LP' in response.text
    assert '>Iniciar sesión</button>' in response.text
    assert "fetch('/api/internal-auth/flotilla/login'" in response.text
    assert 'id="adminMode"' not in response.text
    assert ">Administración</button>" not in response.text
    assert "sessionStorage.setItem(FLOTILLA_ACCESS_KEY" in response.text
    assert "location.replace('/gas-lp/gerentes/inicio')" in response.text
    assert "9 y S son distintos" not in response.text
    assert "Usuario o contraseña incorrectos." in response.text
    assert "ui-monospace" in response.text


def test_manager_list_reads_scopes_without_embedded_relation_cache_dependency():
    backend = (ROOT / "routes/internal_users_mod/users_auth.py").read_text(encoding="utf-8")

    assert '.select("internal_user_id,group_id")' in backend
    assert '.eq("tenant_id", tenant_id)' in backend
    assert '.eq("profile_id", perfil_id)' in backend


def test_manager_landing_separates_fleet_and_expenses():
    response = client.get("/gas-lp/gerentes/inicio")

    assert response.status_code == 200
    assert "<h1>Portal de Gerentes</h1>" in response.text
    assert 'href="/gas-lp/flotilla"' in response.text
    assert 'href="/gas-lp/gerentes/gastos"' in response.text
    assert "Flotilla" in response.text
    assert "Vales y gastos" in response.text


def test_manager_password_reset_is_verified_before_reporting_success():
    backend = (ROOT / "routes/internal_users_mod/users_auth.py").read_text(encoding="utf-8")
    admin_script = (ROOT / "static/js/app/70_admin_catalogs_users.js").read_text(encoding="utf-8")

    assert '"password_verified": True' in backend
    assert "_verify_secret(temp_pin, verified[0].get(\"pin_hash\") or \"\")" in backend
    assert 'data.password_verified !== true' in admin_script
    assert "internal_user_sessions\").delete()" in backend


def test_manager_login_uses_direct_username_lookup_and_scope_fallback():
    backend = (ROOT / "routes/internal_users_mod/users_auth.py").read_text(encoding="utf-8")

    assert '.eq("code", login)' in backend
    assert '.select("group_id")' in backend
    assert 'sb.table("fleet_groups").select("id,name,path")' in backend


def test_fleet_supervision_waits_for_explicit_zone_analysis_and_hides_manager_expenses():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert 'id="managerExpensesLink"' in template
    assert "Selecciona una zona antes de generar el análisis." in script
    assert "$('managerExpensesLink').hidden=true" in script
    assert "await loadReportCatalog({prepare:false,scroll:false})" in script
    assert "$('executiveDashboard').hidden=true" in script
    assert "$('syncButton').hidden=false" in script
    assert "GE CONTROL | Portal de Gerentes" in script
    assert "GE CONTROL | Supervisión de Flotilla" in script


def test_fleet_restores_only_the_last_analysis_generated_today():
    script = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")

    assert "REPORT_CACHE_TTL_MS = 24 * 60 * 60 * 1000" in script
    assert "Se conservará durante el día y mañana podrás generar uno nuevo" in script
    assert "ge_fleet_report_cache:" in script
    assert "saved_at:Date.now()" in script
    assert "data," in script
    assert "renderReportCatalog(cached.data)" in script
    assert "cached.saved_day===todayKey" in script
    assert "Mostrando el análisis guardado de hoy" in script
    assert "flotilla.js?v=20260831-activity-detail-18" in template


def test_fleet_cache_is_scoped_by_zone_and_official_logout_returns_to_supervision():
    script = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert ":zone:" in script
    assert "restoreZoneAnalysis($('reportGroup').value)" in script
    assert "Esta zona todavía no tiene un análisis guardado para hoy" in script
    assert "'/gas-lp/conciliacion?area=flotilla'" in script
    assert "data-driver-search" in script
    assert "runExplorer(button.dataset.driverSearch||'',target)" in script
    assert "renderCompactDriverDetail(data,target)" in script


def test_fleet_expiry_returns_supervision_to_supervision_login():
    timeout = (ROOT / "static/js/session_timeout.js").read_text(encoding="utf-8")
    fleet = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert "localStorage.getItem('ge_gaslp_conciliacion_token')" in timeout
    assert "'/gas-lp/conciliacion?area=flotilla'" in timeout
    assert "authMode==='official'?SUPERVISION_LOGIN_URL:MANAGER_LOGIN_URL" in fleet


def test_fleet_reports_exclude_discarded_events_and_closed_faults():
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert '"coaching_status"' in backend
    assert '"discarded", "dismissed", "rejected", "invalid"' in backend
    assert 'get("is_discarded")' in backend
    assert '"dismiss", "discard", "reject"' in backend
    assert '"uncoachable", "un_coachable"' in backend
    assert "if not row.get(\"cleared_at\")" in backend
    assert '"closed", "cleared", "resolved", "inactive", "dismissed"' in backend
    assert '"current_driver_name", "")' in backend
    assert "Un código PID abierto debe mostrarse" in backend


def test_fleet_dashboard_distinguishes_zero_event_drivers_from_missing_gps():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    analytics = (ROOT / "services/fleet_reports.py").read_text(encoding="utf-8")

    assert "Choferes sin eventos registrados" in template
    assert 'id="safeDrivers"' in template
    assert "drivers_without_events" in frontend
    assert "drivers_without_events" in analytics
    assert "defect.category" in frontend


def test_manager_dashboard_orders_operational_cards_by_priority():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")

    assert template.index('id="driverPrioritiesPanel"') < template.index('id="inspectionPanel"')
    assert template.index('id="inspectionPanel"') < template.index('id="behaviorRanking"')
    assert template.index('id="behaviorRanking"') < template.index('id="safeDriversPanel"')
    assert template.index('id="safeDriversPanel"') < template.index('id="noGpsPanel"')
    assert "Unidades sin actividad GPS en el periodo" in template


def test_manager_dashboard_includes_zone_expense_card():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert 'id="expensesPanel"' in template
    assert "Gastos móviles por unidad" in template
    assert 'id="expenseSummary"' in template
    assert "registeredExpenses" in frontend
    assert '["pending_review", "observed", "accepted", "sent_to_accountant", "paid"]' in backend


def test_manager_portal_has_compact_gps_and_inventory_tabs():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert 'data-manager-tab="gps"' in template
    assert 'data-manager-tab="inventory"' in template
    assert 'data-manager-tab="expenses"' in template
    assert 'id="managerExpensesPanel"' in template
    assert 'id="loadOfficeExpenses"' in template
    assert 'id="managerCompanyName"' in template
    assert 'id="managerCompanyRfc"' in template
    assert 'data-inventory-view="charts"' in template
    assert 'data-inventory-view="physical"' in template
    assert "loadManagerInventory" in frontend
    assert '@router.get("/flotilla/inventory")' in backend
    assert '@router.get("/flotilla/office-expenses")' in backend


def test_manager_gps_keeps_motive_mobile_expenses_separate_from_office_expenses():
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert '== "motive_card"' in backend
    assert 'startswith("ge_control_")' in backend
    assert "Motive no entregó gastos móviles vinculados a unidades" in frontend
    assert "Capturados en GE Control; no provienen de Motive" in frontend
    assert "Gasto por concepto" in frontend
    assert "office-expense-details" in frontend


def test_catalog_exposes_zero_event_drivers_and_expense_totals_to_dashboard():
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert '"drivers_without_events": analytics["drivers_without_events"]' in backend
    assert '"totals": analytics["totals"]' in backend


def test_catalog_recovers_motive_vehicle_links_and_exposes_expenses_by_unit():
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert 'raw_metadata.get("motive_vehicle_id")' in backend
    assert '"vehicle_id,motive_vehicle_id,purchased_at' in backend
    assert '"expense_units": analytics["expense_units"]' in backend
    assert "Desglose por unidad" in frontend
    assert 'row.get("expense_zone_id")' in backend
    assert 'gas_lp_expense_zones' in backend


def test_inspection_dashboard_switches_between_all_pending_and_missing():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert "Realizadas, pendientes y faltantes" in template
    assert "pending_inspection_credits" in frontend
    assert "inspectionViews={all:" in frontend
    assert "missingInspections" in frontend
    assert '"pending_inspection_credits": analytics["pending_inspection_credits"]' in backend


def test_manager_dashboard_exposes_only_excel_and_server_rejects_pdf():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert 'id="zonePdfDownload"' in template
    assert 'data-format="pdf" type="button" hidden' in template
    assert "$('zonePdfDownload').hidden=internal" in frontend
    assert 'ctx.get("identity_type") == "internal" and format != "xlsx"' in backend


def test_motive_sync_refreshes_events_by_updated_after():
    backend = Path("services/motive_sync.py").read_text()
    assert '"updated_after": event_start_date' not in backend
    assert "progress=event_progress" in backend


def test_fleet_sync_ui_shows_phase_pages_and_remaining_time():
    frontend = Path("static/js/gas_lp/flotilla.js").read_text()
    assert "function syncProgressText(sync)" in frontend
    assert "s transcurridos" in frontend
    assert "min restantes" in frontend
    assert "s restantes" in frontend
    assert "Math.min(state.syncEtaDeadline,candidateDeadline)" in frontend
    assert "startSyncCountdown(sync)" in frontend
    assert "Actualización iniciada. Puedes seguir usando el portal." not in frontend
    assert "Actualización completada" in frontend
    assert "'success'" in frontend


def test_manager_portal_localizes_inspections_and_shows_weekly_activity():
    frontend = Path("static/js/gas_lp/flotilla.js").read_text()
    template = Path("templates/flotilla_gas_lp.html").read_text()
    backend = Path("routes/flotilla.py").read_text()

    assert "Antes del viaje" in frontend and "Después del viaje" in frontend
    assert "data-inspection-view" in frontend
    assert "Sin inspección" in frontend
    assert 'id="activityCalendar"' in template
    assert '"activity_calendar": activity_calendar' in backend
    assert "Requieren revisión" in frontend
    assert "Con jornada GPS todos los días laborables" in frontend
    assert "Desglose del día" in frontend
    assert "Recorridos" in frontend and "Paradas" in frontend
    assert '"trip_details": []' in backend
    assert 'daily["stops"]' in backend
    assert "Los domingos son descanso y no cuentan para revisión" in frontend
    assert "const countedDays=days.filter(day=>!isSunday(day))" in frontend
    assert "Datos diarios pendientes de confirmar" in frontend
    assert 'class="activity-complete" open' in frontend
    assert "La tabla muestra los últimos siete días" in frontend
    assert "record.observed===true" in frontend
    assert "activity-mobile-unit" in frontend
    assert '"observed": False' in backend
    assert "Desglose de traspasos" in template


def test_legacy_flotilla_login_redirects_to_dedicated_access():
    response = client.get("/login/gas-lp?intent=flotilla_360&lang=es", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/gas-lp/flotilla/acceso?lang=es"


def test_regular_gas_lp_login_keeps_existing_app_destination():
    response = client.get("/login/gas-lp?intent=administrador")

    assert response.status_code == 200
    assert '"/app" + \'?lang=\'' in response.text


def test_admin_separates_company_motive_settings_from_manager_assignments():
    template = (ROOT / "templates/app/_body.html").read_text(encoding="utf-8")
    script = (ROOT / "static/js/app/70_admin_catalogs_users.js").read_text(encoding="utf-8")

    assert 'id="gasAdminUsersView"' in template
    assert "Motive y zonas" in template
    assert "Configura una sola vez" in template
    assert "aquí solo asignas permisos a este gerente" in template
    assert "document.getElementById('gasAdminUsersView')" in script
