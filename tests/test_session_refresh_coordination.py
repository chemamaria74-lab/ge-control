from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_session_refresh_is_coordinated_across_browser_tabs():
    source = (ROOT / "static/js/session_timeout.js").read_text(encoding="utf-8")

    assert "navigator.locks?.request" in source
    assert "ge-session-refresh" in source
    assert "BroadcastChannel" in source
    assert "tokenAfterWaiting !== tokenBeforeWaiting" in source
    assert "REFRESH_TIMEOUT_MS = 10 * 1000" in source
    assert "controller.abort()" in source
    assert "TAB_IDENTITY_KEY = 'ge_tab_session_user_id'" in source
    assert "refreshedUser !== expected" in source
    assert "headers: {Authorization: `Bearer ${activeToken()}`}" in source


def test_automatic_token_refresh_does_not_count_as_user_activity():
    source = (ROOT / "static/js/session_timeout.js").read_text(encoding="utf-8")
    refreshed = source.split("function applyRefreshedToken", 1)[1].split("if (refreshChannel)", 1)[0]

    assert "markActivity(" not in refreshed


def test_pages_bust_the_session_script_cache_for_the_coordinated_release():
    templates = list((ROOT / "templates").rglob("*.html"))
    consumers = [
        path for path in templates
        if "session_timeout.js" in path.read_text(encoding="utf-8")
    ]

    assert consumers
    for path in consumers:
        html = path.read_text(encoding="utf-8")
        assert "session_timeout.js?v=inactivity-fix-20260901" in html, path
