import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

from services import sw_sapien


def test_consultar_estatus_cfdi_reads_pending_cancellation(monkeypatch):
    class Response:
        content = b'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
        <s:Body><ConsultaResponse xmlns="http://tempuri.org/"><ConsultaResult>
        <CodigoEstatus>S - Comprobante obtenido satisfactoriamente.</CodigoEstatus>
        <Estado>Vigente</Estado><EsCancelable>Cancelable con aceptacion</EsCancelable>
        <EstatusCancelacion>En proceso</EstatusCancelacion>
        </ConsultaResult></ConsultaResponse></s:Body></s:Envelope>'''

        def raise_for_status(self):
            return None

    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(sw_sapien.requests, "post", fake_post)
    result = sw_sapien.consultar_estatus_cfdi(
        uuid_sat="abc", rfc_emisor="AAA010101AAA", rfc_receptor="XAXX010101000",
        total="57199.98", sello_cfdi="abcdefghijklmnop",
    )

    assert result["ok"] is True
    assert result["estado"] == "Vigente"
    assert result["estatus_cancelacion"] == "En proceso"
    body = captured["data"].decode()
    assert "tt=57199.980000" in body
    assert "fe=ijklmnop" in body
