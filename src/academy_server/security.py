"""Local-only access control.

The server can run lesson code, so "any web page can POST to 127.0.0.1" would be
remote code execution. Three gates, all required:

  1. Host allowlist: only 127.0.0.1:<port> / localhost:<port>. Defeats DNS rebinding
     (an attacker domain resolving to 127.0.0.1 still sends its own Host header).
  2. Origin check: a request that carries an Origin must come from our own origin.
     Blocks cross-site fetches and form posts.
  3. Per-launch secret: generated at startup and printed in the launch URL. The browser
     trades it once at /auth for an HttpOnly, SameSite=Strict cookie. Scripts may send it
     as the X-Academy-Token header.

Without a session, a browser page navigation gets a styled HTML 401 (how to get back in);
everything else, including all of /api/, keeps the JSON 401.

Pure ASGI (not BaseHTTPMiddleware) so streaming responses (SSE) pass through untouched.
"""
from __future__ import annotations

import hmac
import json
import secrets
from dataclasses import dataclass, field
from urllib.parse import parse_qs

from .pages import unauthorized_page

COOKIE = "academy_session"
HEADER = b"x-academy-token"
STYLESHEET_PATH = "/static/academy.css"
OPEN_PATHS = frozenset({"/healthz", "/auth", STYLESHEET_PATH})   # CSS isn't sensitive; the 401 page needs it
SECURITY_HEADERS = ((b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def safe_next(raw: str | None) -> str:
    """Where /auth may redirect: a same-origin path only, else "/".

    Rejects anything a browser could turn into another origin: "//host", "/<BACKSLASH>host"
    (browsers read a backslash as a slash), "https:...", "javascript:...", and tab/newline/space or
    other control characters (browsers strip some of them, so "/<TAB>/host" becomes "//host").
    Only printable ASCII, so the Location header is always plain bytes.
    """
    if not raw or len(raw) > 2048 or raw[0] != "/" or raw[1:2] == "/":
        return "/"
    if "\\" in raw or any(not 0x21 <= ord(ch) <= 0x7E for ch in raw):
        return "/"
    return raw


@dataclass
class SecurityConfig:
    token: str
    port: int
    extra_hosts: list[str] = field(default_factory=list)     # e.g. "testserver" in tests
    extra_origins: list[str] = field(default_factory=list)   # e.g. the Vite dev server
    open_prefixes: tuple[str, ...] = ()                      # e.g. "/relay/" (has its own auth)

    @property
    def allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}", *self.extra_hosts}

    @property
    def allowed_origins(self) -> set[str]:
        return {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}", *self.extra_origins}

    def token_ok(self, candidate: str | None) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self.token.encode())


def _headers(scope) -> dict[bytes, bytes]:
    return {k.lower(): v for k, v in scope.get("headers", [])}


def _cookie(raw: bytes | None, name: str) -> str | None:
    if not raw:
        return None
    for part in raw.decode("latin-1").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None


async def _send_json(send, status: int, body: dict, extra_headers: list[tuple[bytes, bytes]] = ()) -> None:
    data = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode()),
                            (b"cache-control", b"no-store"), *extra_headers]})
    await send({"type": "http.response.body", "body": data})


async def _send_html(send, status: int, page: str) -> None:
    data = page.encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/html; charset=utf-8"),
                            (b"content-length", str(len(data)).encode()), (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": data})


def _is_page_navigation(scope, headers: dict[bytes, bytes]) -> bool:
    """A browser loading a page (not fetch/XHR, not the API): gets the HTML 401 instead of JSON."""
    if scope.get("method") != "GET" or scope.get("path", "").startswith(("/api/", "/relay/")):
        return False
    mode = headers.get(b"sec-fetch-mode")
    if mode is not None:
        return mode == b"navigate"
    return b"text/html" in headers.get(b"accept", b"")


def _with_security_headers(send):
    """Add the hardening headers to every HTTP response (open paths and errors included)."""
    async def wrapped(message):
        if message["type"] == "http.response.start":
            present = {k.lower() for k, _ in message.get("headers", [])}
            message["headers"] = [*message.get("headers", []),
                                  *((k, v) for k, v in SECURITY_HEADERS if k not in present)]
        await send(message)
    return wrapped


class LocalOnlyMiddleware:
    def __init__(self, app, config: SecurityConfig):
        self.app = app
        self.cfg = config

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        if scope["type"] == "http":
            send = _with_security_headers(send)
        headers = _headers(scope)
        host = headers.get(b"host", b"").decode("latin-1")
        if host not in self.cfg.allowed_hosts:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            return await _send_json(send, 400, {"error": "bad_host", "detail": "use http://127.0.0.1:<port>"})
        origin = headers.get(b"origin")
        if origin is not None and origin.decode("latin-1") not in self.cfg.allowed_origins:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            return await _send_json(send, 403, {"error": "bad_origin"})

        path = scope.get("path", "")
        if path == "/auth" and scope["type"] == "http":
            return await self._auth(scope, headers, send)
        if path in OPEN_PATHS or path.startswith(self.cfg.open_prefixes):  # () matches nothing
            return await self.app(scope, receive, send)

        supplied = headers.get(HEADER, b"").decode("latin-1") or _cookie(headers.get(b"cookie"), COOKIE)
        if not self.cfg.token_ok(supplied):
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            if _is_page_navigation(scope, headers):
                return await _send_html(send, 401, unauthorized_page(self.cfg.port))
            return await _send_json(send, 401, {
                "error": "unauthorized",
                "detail": "open the launch URL printed by `python run.py` (or run `labctl open`)"})

        return await self.app(scope, receive, send)

    async def _auth(self, scope, headers, send) -> None:
        """GET /auth?t=<token>[&next=/path]: set the session cookie, then redirect to `next`
        (default /). The redirect also drops the token from the URL bar."""
        qs = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
        token = (qs.get("t") or [None])[0]
        if not self.cfg.token_ok(token):
            if _is_page_navigation(scope, headers):
                return await _send_html(send, 401, unauthorized_page(self.cfg.port, reason="bad_token"))
            return await _send_json(send, 401, {"error": "bad_token"})
        target = safe_next((qs.get("next") or [None])[0])
        cookie = f"{COOKIE}={self.cfg.token}; Path=/; HttpOnly; SameSite=Strict"
        await send({"type": "http.response.start", "status": 303,
                    "headers": [(b"location", target.encode("ascii")), (b"set-cookie", cookie.encode()),
                                (b"cache-control", b"no-store"), (b"content-length", b"0")]})
        await send({"type": "http.response.body", "body": b""})
