import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from services import sw_sapien


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _patch_audit(monkeypatch):
    calls = {"requests": [], "responses": [], "versions": []}

    def record_request(**kwargs):
        calls["requests"].append(kwargs)
        return len(calls["requests"])

    def record_response(**kwargs):
        calls["responses"].append(kwargs)
        return len(calls["responses"])

    def version_xml(**kwargs):
        calls["versions"].append(kwargs)

    monkeypatch.setattr(sw_sapien, "record_pac_request", record_request)
    monkeypatch.setattr(sw_sapien, "record_pac_response", record_response)
    monkeypatch.setattr(sw_sapien, "version_xml", version_xml)
    return calls


def test_emitir_timbrar_json_records_pac_request_response_and_xml_version(monkeypatch):
    calls = _patch_audit(monkeypatch)
    monkeypatch.setattr(sw_sapien, "_get_token", lambda: "token-test")
    monkeypatch.setattr(
        sw_sapien.requests,
        "post",
        lambda *args, **kwargs: _FakeResponse(
            {
                "status": "success",
                "data": {
                    "uuid": "UUID-OK",
                    "cfdi": "<cfdi:Comprobante Version=\"4.0\"/>",
                    "pdfUrl": "https://pac.example/cfdi.pdf",
                },
            }
        ),
    )

    result = sw_sapien.emitir_timbrar_json(
        {"Version": "4.0", "Emisor": {"Rfc": "AAA010101AAA"}, "Receptor": {"Rfc": "XAXX010101000"}, "Conceptos": [{"ClaveProdServ": "78101800"}]}
    )

    assert result["ok"] is True
    assert calls["requests"][0]["operation"] == "stamp_json"
    assert calls["responses"][0]["request_id"] == 1
    assert calls["responses"][0]["status"] == "ok"
    assert calls["responses"][0]["uuid_sat"] == "UUID-OK"
    assert calls["versions"][0]["uuid_sat"] == "UUID-OK"
    assert calls["versions"][0]["xml_content"].startswith("<cfdi:Comprobante")


def test_emitir_timbrar_json_returns_controlled_error_but_audits_raw_payload(monkeypatch):
    calls = _patch_audit(monkeypatch)
    monkeypatch.setattr(sw_sapien, "_get_token", lambda: "token-test")
    raw_error = "<!doctype html><html>Traceback token=secret <cfdi:Comprobante/></html>"
    monkeypatch.setattr(
        sw_sapien.requests,
        "post",
        lambda *args, **kwargs: _FakeResponse(ValueError("not json"), status_code=500, text=raw_error),
    )

    result = sw_sapien.emitir_timbrar_json(
        {"Version": "4.0", "Emisor": {"Rfc": "AAA010101AAA"}, "Receptor": {"Rfc": "XAXX010101000"}, "Conceptos": [{"ClaveProdServ": "78101800"}]}
    )

    assert result["ok"] is False
    assert "Traceback" not in result["error"]
    assert "<cfdi:" not in result["error"]
    assert "token=secret" not in result["error"]
    assert calls["responses"][0]["status"] == "error"
    assert calls["responses"][0]["response_payload"]["message"] == raw_error
    assert calls["responses"][0]["error_message"] == result["error"]


def test_timbrar_cfdi_error_includes_message_detail(monkeypatch):
    calls = _patch_audit(monkeypatch)
    monkeypatch.setattr(sw_sapien, "_get_token", lambda: "token-test")
    monkeypatch.setattr(
        sw_sapien.requests,
        "post",
        lambda *args, **kwargs: _FakeResponse(
            {
                "status": "error",
                "message": "CP999 - Error no clasificado.",
                "messageDetail": "The element 'Impuestos' has invalid child element 'Retenciones'.",
                "data": None,
            },
            status_code=400,
            text='{"status":"error"}',
        ),
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" '
        'SubTotal="1.00" Moneda="MXN" Total="1.00" TipoDeComprobante="I" '
        'Exportacion="01" LugarExpedicion="20000">'
        '<cfdi:Emisor Rfc="AAA010101AAA" Nombre="EMISOR" RegimenFiscal="601"/>'
        '<cfdi:Receptor Rfc="XAXX010101000" Nombre="PUBLICO EN GENERAL" '
        'DomicilioFiscalReceptor="20000" RegimenFiscalReceptor="616" UsoCFDI="S01"/>'
        '<cfdi:Conceptos><cfdi:Concepto ClaveProdServ="78101802" Cantidad="1" '
        'ClaveUnidad="E48" Descripcion="SERVICIO" ValorUnitario="1.00" Importe="1.00" '
        'ObjetoImp="01"/></cfdi:Conceptos></cfdi:Comprobante>'
    )

    result = sw_sapien.timbrar_cfdi(xml)

    assert result["error"].startswith("CP999")
    assert "Detalle:" in result["error"]
    assert "invalid child element" in result["error"]
    assert calls["responses"][0]["error_message"] == result["error"]


def test_cancelar_cfdi_controlled_validation_error_records_request_and_response(monkeypatch):
    calls = _patch_audit(monkeypatch)

    result = sw_sapien.cancelar_cfdi(
        "11111111-2222-3333-4444-555555555555",
        "AAA010101AAA",
        motivo="99",
        module="transporte",
        user_id="user-1",
        perfil_id=7,
    )

    assert result["ok"] is False
    assert result["pac_request_id"] == 1
    assert result["pac_response_id"] == 1
    assert calls["requests"][0]["operation"] == "cancel"
    assert calls["responses"][0]["request_id"] == 1
    assert calls["responses"][0]["status"] == "error"
    assert "Motivo SAT inválido" in result["error"]
