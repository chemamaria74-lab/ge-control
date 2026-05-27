import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from services.sat_sync_worker import SatSyncWindow, ingest_manual_sat_xmls, parse_cfdi_minimal


SAT_XML_GAS_LP = """<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
  xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="4.0" Fecha="2026-05-20T12:00:00" TipoDeComprobante="I" Total="1160.00" Moneda="MXN" MetodoPago="PUE" FormaPago="03">
  <cfdi:Emisor Rfc="AAA010101AAA" Nombre="PROVEEDOR GAS LP" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="BBB010101BBB" Nombre="EMPRESA RECEPTORA" DomicilioFiscalReceptor="20000" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15111510" Cantidad="1000" ClaveUnidad="LTR" Unidad="Litro" Descripcion="Gas LP" ValorUnitario="1.00" Importe="1000.00" ObjetoImp="02"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="11111111-2222-3333-4444-555555555555" FechaTimbrado="2026-05-20T12:01:00"/>
  </cfdi:Complemento>
</cfdi:Comprobante>
"""


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _Table:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.filters = {}
        self.pending_insert = None
        self.pending_update = None
        self._limit = None

    def insert(self, row):
        self.pending_insert = row
        return self

    def update(self, row):
        self.pending_update = row
        return self

    def select(self, _columns):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def execute(self):
        rows = self.db.setdefault(self.name, [])
        if self.pending_insert is not None:
            row = dict(self.pending_insert)
            row.setdefault("id", f"{self.name}-{len(rows) + 1}")
            rows.append(row)
            return _Result([row])
        selected = [row for row in rows if all(row.get(k) == v for k, v in self.filters.items())]
        if self.pending_update is not None:
            for row in selected:
                row.update(self.pending_update)
            return _Result(selected)
        if self._limit is not None:
            selected = selected[: self._limit]
        return _Result(selected)


class _FakeSupabase:
    def __init__(self):
        self.db = {}

    def table(self, name):
        return _Table(self.db, name)


def _window():
    return SatSyncWindow(
        tenant_id="00000000-0000-0000-0000-000000000001",
        company_id="00000000-0000-0000-0000-000000000001",
        perfil_id=7,
        provider="manual",
        date_from=datetime(2026, 5, 20, tzinfo=timezone.utc),
        date_to=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )


def test_parse_cfdi_minimal_maps_sat_type_and_uuid():
    parsed = parse_cfdi_minimal(SAT_XML_GAS_LP)

    assert parsed["uuid"] == "11111111-2222-3333-4444-555555555555"
    assert parsed["tipo"] == "ingreso"
    assert parsed["rfc_emisor"] == "AAA010101AAA"
    assert parsed["fingerprint"]


def test_ingest_manual_sat_xml_creates_inbox_and_detected_load():
    fake = _FakeSupabase()

    result = ingest_manual_sat_xmls(
        sb=fake,
        window=_window(),
        xml_items=[{"filename": "gas_lp.xml", "content": SAT_XML_GAS_LP.encode("utf-8")}],
        created_by="user-1",
    )

    assert result["ok"] is True
    assert result["inserted"] == 1
    assert result["duplicates"] == 0
    assert result["detected_loads"] == 1
    assert fake.db["cfdi_sat_inbox"][0]["uuid"] == "11111111-2222-3333-4444-555555555555"
    assert fake.db["cfdi_sat_inbox"][0]["processed_status"] == "load_draft_created"
    assert fake.db["detected_loads"][0]["litros_detectados"] == 1000.0
    assert fake.db["sat_sync_jobs"][0]["status"] == "completed"


def test_ingest_manual_sat_xml_deduplicates_by_uuid():
    fake = _FakeSupabase()
    ingest_manual_sat_xmls(sb=fake, window=_window(), xml_items=[{"filename": "a.xml", "content": SAT_XML_GAS_LP}], created_by="user-1")

    result = ingest_manual_sat_xmls(
        sb=fake,
        window=_window(),
        xml_items=[{"filename": "b.xml", "content": SAT_XML_GAS_LP}],
        created_by="user-1",
    )

    assert result["inserted"] == 0
    assert result["duplicates"] == 1
    assert len(fake.db["cfdi_sat_inbox"]) == 1
    assert len(fake.db["detected_loads"]) == 1
