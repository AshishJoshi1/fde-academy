"""The thin relay: lesson code -> this server -> the gateway -> Claude.

It's a tiny LLM gateway, the same kind of job LiteLLM does in front of Claude for you:
1. **Key isolation.** Lesson code gets a dummy key and ANTHROPIC_BASE_URL pointing here
   (/relay/<run token>). The relay drops the incoming Authorization header and adds the
   real key on the way out.
2. **Observation.** Each call is recorded as two run events, in order: the exact request
   (body and headers, minus credentials), then the exact response (body, or every
   server-sent event of a stream), with status, gateway headers, timing, usage and cost.
   That works for any SDK path (create, stream, tool runner), because it's on the wire.

It doesn't cache, replay, retry, rewrite or budget. The SDK retries, and the gateway
enforces the key's budget and rate limits.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .pricing import Pricing
from .runs import Run, RunManager

# Hop-by-hop and framing headers are per-connection; never forward them.
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
        "transfer-encoding", "upgrade", "host", "content-length", "content-encoding", "accept-encoding"}
_CREDENTIALS = {"authorization", "x-api-key", "cookie"}


@dataclass(frozen=True)
class Upstream:
    base_url: str
    api_key: str = field(repr=False)   # never in a repr, log line or error


def _error(status: int, kind: str, message: str) -> JSONResponse:
    """Errors shaped like Anthropic's, so the SDK raises the usual exception classes."""
    return JSONResponse({"type": "error", "error": {"type": kind, "message": message}}, status_code=status)


def _json_or_text(raw: bytes) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return raw.decode("utf-8", "replace")


def _recorded(headers: httpx.Headers | Any, drop: set[str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items() if k.lower() not in drop}


def parse_sse(text: str) -> list[dict[str, Any]]:
    """Split a server-sent event stream into [{event, data}] (data parsed as JSON when it is)."""
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if name or data:
            events.append({"event": name, "data": _json_or_text("\n".join(data).encode())})
    return events


def stream_usage(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A stream's usage: message_start carries the input side, message_delta the final output count."""
    usage: dict[str, Any] = {}
    for ev in events:
        data = ev["data"] if isinstance(ev["data"], dict) else {}
        if ev["event"] == "message_start":
            usage.update((data.get("message") or {}).get("usage") or {})
        elif ev["event"] == "message_delta":
            usage.update({k: v for k, v in (data.get("usage") or {}).items() if v is not None})
    return usage or None


def build_router(manager: RunManager, upstream: Upstream | None, client: Callable[[], httpx.AsyncClient],
                 pricing: Pricing, store: Any, credentials_hint: str) -> APIRouter:
    router = APIRouter()

    def record_result(run: Run, call: int, model: str | None, status: int, headers: httpx.Headers,
                      body: Any, started: float, usage: dict[str, Any] | None, stream: bool) -> None:
        # cost_usd None on a successful call means the model has no entry in pricing.yaml.
        cost = pricing.cost_usd(model, usage) if status < 400 else None
        run.emit("llm.response", call=call, status=status, stream=stream,
                 ms=int((time.monotonic() - started) * 1000), headers=_recorded(headers, {"set-cookie"}),
                 body=body, usage=usage, cost_usd=cost)
        if cost:
            run.add_cost(cost)
            store.record_spend("run", cost, run_id=run.id, model=model, usage=usage)

    @router.api_route("/relay/{token}/{path:path}", methods=["GET", "POST"], include_in_schema=False)
    async def relay(token: str, path: str, request: Request):
        run = manager.by_token(token)
        if run is None:
            return _error(401, "authentication_error", "unknown or finished run: the relay only serves active runs")
        if not path.startswith("v1/"):
            return _error(404, "not_found_error", f"the relay forwards Anthropic API paths only (/v1/...), not /{path}")
        if upstream is None:
            return _error(503, "api_error", f"no gateway credentials: {credentials_hint}")

        raw = await request.body()
        body = _json_or_text(raw) if raw else None
        stream = isinstance(body, dict) and body.get("stream") is True
        model = body.get("model") if isinstance(body, dict) else None
        call = run.next_call()
        run.emit("llm.request", call=call, method=request.method, path="/" + path,
                 query=request.url.query or None, headers=_recorded(request.headers, _CREDENTIALS | _HOP),
                 body=body)

        headers = {k: v for k, v in request.headers.items() if k.lower() not in _CREDENTIALS | _HOP}
        headers["authorization"] = f"Bearer {upstream.api_key}"
        url = f"{upstream.base_url.rstrip('/')}/{path}"
        if request.url.query:
            url += "?" + request.url.query
        started = time.monotonic()
        upstream_req = client().build_request(request.method, url, content=raw, headers=headers)
        try:
            resp = await client().send(upstream_req, stream=stream)
        except httpx.HTTPError as exc:
            run.emit("llm.error", call=call, ms=int((time.monotonic() - started) * 1000),
                     error=f"{type(exc).__name__}: {exc}")
            return _error(502, "api_error", f"the relay could not reach the gateway: {type(exc).__name__}")

        passthrough = {k: v for k, v in resp.headers.items() if k.lower() not in _HOP | {"set-cookie"}}
        if not stream:
            resp_body = _json_or_text(resp.content)
            usage = resp_body.get("usage") if isinstance(resp_body, dict) else None
            record_result(run, call, model, resp.status_code, resp.headers, resp_body, started, usage, False)
            return Response(content=resp.content, status_code=resp.status_code, headers=passthrough)

        async def relay_stream():
            chunks: list[bytes] = []
            try:
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    yield chunk
            finally:
                await resp.aclose()
                events = parse_sse(b"".join(chunks).decode("utf-8", "replace"))
                record_result(run, call, model, resp.status_code, resp.headers,
                              {"events": events}, started, stream_usage(events), True)

        return StreamingResponse(relay_stream(), status_code=resp.status_code, headers=passthrough)

    return router
