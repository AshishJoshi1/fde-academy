"""The mock Meridian API as a lesson fixture: vendored unchanged, started per run with its own
token, and every request it answers reported in order."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from academy_server import fixtures

PROJECT_COPY = Path(r"C:\Users\AshishKumarJoshi\FDE\Projects\04-proposal-builder")
VENDORED = Path(fixtures.__file__).resolve().parent / "meridian"


@pytest.fixture
def meridian():
    seen: list[dict] = []
    fx = fixtures.start("meridian", on_request=lambda **d: seen.append(d))
    yield fx, seen
    fx.stop()


def get(fx, path: str, token: str | None = None) -> httpx.Response:
    token = fx.env["MERIDIAN_API_TOKEN"] if token is None else token
    return httpx.get(fx.url + path, headers={"Authorization": f"Bearer {token}"}, timeout=5, trust_env=False)


def test_it_serves_the_seed_with_this_runs_token(meridian):
    fx, seen = meridian
    assert fx.env == {"MERIDIAN_API_URL": fx.url, "MERIDIAN_API_TOKEN": fx.env["MERIDIAN_API_TOKEN"]}
    r = get(fx, "/opportunities/OPP-1042")
    assert r.status_code == 200 and r.json()["account_id"] == "ACC-017" and r.json()["requested_discount_pct"] == 12
    assert get(fx, "/opportunities/OPP-0000").status_code == 404
    assert get(fx, "/opportunities/OPP-1042", token="local-mock-token").status_code == 401   # not the default
    assert [(d["method"], d["path"], d["status"]) for d in seen] == [
        ("GET", "/opportunities/OPP-1042", 200), ("GET", "/opportunities/OPP-0000", 404),
        ("GET", "/opportunities/OPP-1042", 401)]
    assert seen[0]["body"] == r.json() and seen[0]["query"] is None
    assert fx.env["MERIDIAN_API_TOKEN"] not in repr(fx)


def test_the_seed_reads_as_utf8():
    names = [a["legal_name"] for a in fixtures.load_seed()["accounts"]]
    assert any("Łódź" in n for n in names) or any("ł" in n.lower() for n in names)


def test_each_run_gets_its_own_token_and_port(meridian):
    fx, _ = meridian
    other = fixtures.start("meridian")
    try:
        assert other.url != fx.url and other.env["MERIDIAN_API_TOKEN"] != fx.env["MERIDIAN_API_TOKEN"]
    finally:
        other.stop()
    with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
        get(other, "/accounts")


def test_unknown_fixture():
    with pytest.raises(ValueError, match="unknown fixture"):
        fixtures.start("nope")


@pytest.mark.skipif(not PROJECT_COPY.is_dir(), reason="the Projects folder isn't on this machine")
def test_vendored_copy_is_unchanged():
    assert (VENDORED / "meridian_api.py").read_bytes() == (PROJECT_COPY / "mock_api" / "meridian_api.py").read_bytes()
    for name in ("accounts", "opportunities", "rate_card"):
        assert (VENDORED / "seed" / f"{name}.json").read_bytes() == \
            (PROJECT_COPY / "samples" / "seed" / f"{name}.json").read_bytes()
