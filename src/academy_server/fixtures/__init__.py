"""Lesson fixtures: services a lesson's code calls, started by the lab beside the lesson process.

A step asks for one with `run: {fixture: meridian}` in its step.yaml. The lab starts a fresh one
for each run, on a free port with a fresh token, gives the lesson process its URL and token as
environment variables, and stops it when the run ends. Every request it serves is reported to
on_request before the response goes out, so the run's events keep the true order:
model call, the tool's API request, the next model call.

Standard library only, like the vendored API, so tools/run_live.py can start it too.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .meridian import meridian_api

MERIDIAN_SEED = Path(__file__).resolve().parent / "meridian" / "seed"
NAMES = ("meridian",)


@dataclass
class Fixture:
    name: str
    url: str
    env: dict[str, str] = field(repr=False)   # for the lesson process; holds the token
    server: ThreadingHTTPServer = field(repr=False)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def load_seed(seed_dir: Path = MERIDIAN_SEED) -> dict[str, Any]:
    """The vendored loader reads with the locale's encoding; the seed has "Łódź", so read UTF-8 here."""
    return {name: json.loads((seed_dir / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("accounts", "opportunities", "rate_card")}


def start_meridian(on_request: Callable[..., None] | None = None) -> Fixture:
    """The mock Meridian API on 127.0.0.1, in a background thread. on_request(method, path, query,
    status, body) is called for every request it answers. Its own request log goes to os.devnull:
    the run's events are the log."""
    token = secrets.token_urlsafe(16)
    base = meridian_api.make_handler(load_seed(), os.devnull)

    class Handler(base):  # type: ignore[misc, valid-type]
        def _authorised(self) -> bool:            # this run's token, not the module-level default
            return self.headers.get("Authorization") == f"Bearer {token}"

        def _send(self, status: int, body: Any) -> None:
            if on_request is not None:
                url = urlparse(self.path)
                on_request(method=self.command, path=url.path, query=url.query or None, status=status, body=body)
            super()._send(status, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="meridian-api").start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    return Fixture(name="meridian", url=url, server=server,
                   env={"MERIDIAN_API_URL": url, "MERIDIAN_API_TOKEN": token})


def start(name: str, on_request: Callable[..., None] | None = None) -> Fixture:
    if name == "meridian":
        return start_meridian(on_request)
    raise ValueError(f"unknown fixture {name!r}; known: {', '.join(NAMES)}")
