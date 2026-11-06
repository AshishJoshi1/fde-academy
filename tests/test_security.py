from conftest import PORT, TOKEN


def test_healthz_is_open(make_client):
    c = make_client(authed=False)
    assert c.get("/healthz").json()["ok"] is True


def test_api_requires_token(make_client):
    c = make_client(authed=False)
    r = c.get("/api/status")
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    assert c.get("/api/status", headers={"x-academy-token": "wrong"}).status_code == 401
    assert c.get("/api/status", headers={"x-academy-token": TOKEN}).status_code == 200


def test_auth_sets_strict_cookie_and_strips_token(make_client):
    c = make_client(authed=False)
    assert c.get("/auth", params={"t": "nope"}, follow_redirects=False).status_code == 401
    r = c.get("/auth", params={"t": TOKEN}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert c.get("/api/status").status_code == 200          # cookie now carried by the client


def test_bad_host_rejected_even_with_token(make_client):
    """DNS rebinding: attacker.example resolving to 127.0.0.1 still sends its own Host header."""
    c = make_client()
    r = c.get("/api/status", headers={"host": "attacker.example"})
    assert r.status_code == 400 and r.json()["error"] == "bad_host"
    assert c.get("/healthz", headers={"host": f"127.0.0.1:{PORT}"}).status_code == 200


def test_cross_origin_rejected_even_with_token(make_client):
    c = make_client()
    r = c.put("/api/steps/m02.lab02.s01/files/main.py", json={"code": "x"},
              headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"] == "bad_origin"
    ok = c.put("/api/steps/m02.lab02.s01/files/main.py", json={"code": "x"},
               headers={"origin": f"http://127.0.0.1:{PORT}"})
    assert ok.status_code == 200


def test_security_headers_present(make_client):
    r = make_client().get("/api/status")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"


# ---------------------------------------------------------------- browser pages
import pytest

from academy_server.security import safe_next

NAV = {"accept": "text/html,application/xhtml+xml", "sec-fetch-mode": "navigate"}


def test_stylesheet_is_open_and_hardened(make_client):
    r = make_client(authed=False).get("/static/academy.css")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")
    assert "--accent" in r.text and "light-dark(" in r.text
    assert r.headers["x-content-type-options"] == "nosniff"     # open paths get the headers too


def test_browser_navigation_gets_html_401_without_the_token(make_client):
    c = make_client(authed=False)
    r = c.get("/", headers=NAV)
    assert r.status_code == 401 and r.headers["content-type"].startswith("text/html")
    assert 'href="/static/academy.css"' in r.text and "launch link" in r.text
    assert TOKEN not in r.text
    assert r.headers["x-frame-options"] == "DENY"


def test_api_keeps_json_401_even_for_html_accept(make_client):
    c = make_client(authed=False)
    r = c.get("/api/status", headers=NAV)
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    r = c.get("/", headers={"accept": "text/html", "sec-fetch-mode": "cors"})   # fetch(), not navigation
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"


def test_stale_launch_link_gets_html_page(make_client):
    r = make_client(authed=False).get("/auth", params={"t": "old-token"}, headers=NAV, follow_redirects=False)
    assert r.status_code == 401 and "earlier start" in r.text


@pytest.mark.parametrize("raw, expected", [
    (None, "/"), ("", "/"),
    ("/design", "/design"), ("/design?theme=dark#why", "/design?theme=dark#why"), ("/%2F%2Fx", "/%2F%2Fx"),
    ("//evil.example", "/"), ("/\\evil.example", "/"), ("\\\\evil.example", "/"), ("/x\\y", "/"),
    ("https://evil.example", "/"), ("javascript:alert(1)", "/"), ("design", "/"),
    ("/\t/evil.example", "/"), ("/\n/evil.example", "/"), ("/ /evil.example", "/"), ("/caf\u00e9", "/"),
    ("/" + "a" * 3000, "/"),
])
def test_safe_next(raw, expected):
    assert safe_next(raw) == expected


def test_auth_redirects_to_safe_next_only(make_client):
    c = make_client(authed=False)
    r = c.get("/auth", params={"t": TOKEN, "next": "/design"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/design"
    r = c.get("/auth", params={"t": TOKEN, "next": "//evil.example/x"}, follow_redirects=False)
    assert r.headers["location"] == "/"
