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
    r = c.put("/api/steps/m02.lab02.s01/draft", json={"filename": "main.py", "code": "x"},
              headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"] == "bad_origin"
    ok = c.put("/api/steps/m02.lab02.s01/draft", json={"filename": "main.py", "code": "x"},
               headers={"origin": f"http://127.0.0.1:{PORT}"})
    assert ok.status_code == 200


def test_security_headers_present(make_client):
    r = make_client().get("/api/status")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
