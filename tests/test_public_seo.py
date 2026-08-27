import json
import os
import re

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-publishable-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from main import app


client = TestClient(app)


def test_landing_exposes_canonical_social_metadata_and_structured_data():
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers.get("x-robots-tag") is None
    html = response.text
    assert '<link rel="canonical" href="https://gecontrol.mx/">' in html
    assert '<meta property="og:url" content="https://gecontrol.mx/">' in html
    assert '<meta property="og:image" content="https://gecontrol.mx/static/img/ge-icon-512.png">' in html

    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    graph = json.loads(match.group(1))["@graph"]
    assert any(item.get("@type") == "Organization" for item in graph)
    assert sum(item.get("@type") == "SoftwareApplication" for item in graph) == 2


def test_robots_points_to_sitemap_and_blocks_private_areas():
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "Disallow: /api/" in response.text
    assert "Disallow: /admin-saas" in response.text
    assert "Sitemap: https://gecontrol.mx/sitemap.xml" in response.text


def test_sitemap_contains_only_current_public_commercial_page():
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<loc>https://gecontrol.mx/</loc>" in response.text
    assert "<loc>https://gecontrol.mx/facturacion-recurrente</loc>" in response.text
    assert "<loc>https://gecontrol.mx/software-carta-porte</loc>" in response.text
    assert "<loc>https://gecontrol.mx/control-de-transporte</loc>" in response.text
    assert "<loc>https://gecontrol.mx/recursos</loc>" in response.text
    assert "<loc>https://gecontrol.mx/recursos/automatizar-facturas-recurrentes</loc>" in response.text
    assert "<loc>https://gecontrol.mx/recursos/carta-porte-31</loc>" in response.text
    assert "<loc>https://gecontrol.mx/recursos/cfdi-ingreso-vs-traslado</loc>" in response.text
    assert response.text.count("<url>") == 8


def test_private_pages_emit_noindex_header():
    response = client.get("/choice")

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_legal_language_variants_stay_accessible_but_out_of_index():
    response = client.get("/privacy?lang=es")

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_public_solution_pages_are_indexable_and_have_unique_canonicals():
    pages = {
        "/facturacion-recurrente": "https://gecontrol.mx/facturacion-recurrente",
        "/software-carta-porte": "https://gecontrol.mx/software-carta-porte",
        "/control-de-transporte": "https://gecontrol.mx/control-de-transporte",
    }

    for path, canonical in pages.items():
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers.get("x-robots-tag") is None
        assert f'<link rel="canonical" href="{canonical}">' in response.text
        assert response.text.count("<h1>") == 1


def test_existing_operational_routes_remain_available_and_noindex():
    for path in ("/choice", "/login", "/transporte-v2/login-admin"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_resource_pages_are_indexable_unique_and_cite_official_sources():
    pages = {
        "/recursos": "https://gecontrol.mx/recursos",
        "/recursos/automatizar-facturas-recurrentes": "https://gecontrol.mx/recursos/automatizar-facturas-recurrentes",
        "/recursos/carta-porte-31": "https://gecontrol.mx/recursos/carta-porte-31",
        "/recursos/cfdi-ingreso-vs-traslado": "https://gecontrol.mx/recursos/cfdi-ingreso-vs-traslado",
    }
    titles = set()

    for path, canonical in pages.items():
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers.get("x-robots-tag") is None
        assert f'<link rel="canonical" href="{canonical}">' in response.text
        title = re.search(r"<title>(.*?)</title>", response.text).group(1)
        assert title not in titles
        titles.add(title)

    for path in tuple(pages)[1:]:
        assert "sat.gob.mx" in client.get(path).text
