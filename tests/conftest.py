from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Isolated learner data dir: never touch the real %LOCALAPPDATA%\\fde-academy."""
    monkeypatch.setenv("FDE_ACADEMY_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def store(home):
    from academy_server.store import Store
    s = Store(home / "academy.db")
    yield s
    s.close()


TOKEN = "test-token-123"
PORT = 8787


@pytest.fixture
def make_client(home):
    from fastapi.testclient import TestClient
    from academy_server.app import AppSettings, create_app

    clients = []

    def _make(content_dir: Path = REPO / "content", web_dist: Path | None = None, authed: bool = True):
        settings = AppSettings(token=TOKEN, port=PORT, content_dir=content_dir, db_path=home / "academy.db",
                               web_dist=web_dist or (home / "no-web"), extra_hosts=["testserver"])
        client = TestClient(create_app(settings), base_url="http://testserver")
        if authed:
            client.headers["x-academy-token"] = TOKEN
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)
