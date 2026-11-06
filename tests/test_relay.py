"""The thin relay in isolation: a fake gateway (httpx.MockTransport), no lesson process."""
import json

import httpx

from academy_server.relay import Upstream, parse_sse, stream_usage
from academy_server.runs import Run

REAL_KEY = "sk-real-key-only-the-relay-holds"
MESSAGE = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
           "content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn", "stop_sequence": None,
           "usage": {"input_tokens": 22, "output_tokens": 66, "cache_creation_input_tokens": 0,
                     "cache_read_input_tokens": 0}}
SSE = ('event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":22,"output_tokens":1}}}\n\n'
       'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hi"}}\n\n'
       'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":66}}\n\n'
       'event: message_stop\ndata: {"type":"message_stop"}\n\n')


class FakeGateway:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if json.loads(request.content or b"{}").get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=SSE.encode())
        return httpx.Response(200, json=MESSAGE, headers={"x-litellm-call-id": "call-123"})


def active_run(client, tmp_path) -> Run:
    """Register a run as if the runner had started it (the relay only serves active runs)."""
    run = Run(id="r-test", token="tok-test", step_id="m02.lab02.s01", module_id="m02", model="claude-opus-5-5",
              entry="main.py", playground=tmp_path, timeout_s=5)
    manager = client.app.state.manager
    manager._active[run.token] = run
    manager._runs[run.id] = run
    return run


def test_unknown_run_token_is_refused_with_an_anthropic_shaped_error(make_client):
    r = make_client(authed=False).post("/relay/not-a-run/v1/messages", json={})
    assert r.status_code == 401
    assert r.json() == {"type": "error", "error": {"type": "authentication_error",
                                                   "message": "unknown or finished run: the relay only serves active runs"}}


def test_only_api_paths_are_forwarded(make_client, tmp_path):
    c = make_client(authed=False, upstream=Upstream("https://gw.example", REAL_KEY),
                    upstream_transport=httpx.MockTransport(FakeGateway()))
    active_run(c, tmp_path)
    r = c.post("/relay/tok-test/admin/keys", json={})
    assert r.status_code == 404 and r.json()["error"]["type"] == "not_found_error"


def test_missing_credentials_give_a_clear_503(make_client, tmp_path):
    c = make_client(authed=False)
    active_run(c, tmp_path)
    r = c.post("/relay/tok-test/v1/messages", json={"model": "claude-opus-5-5"})
    assert r.status_code == 503 and "anthropic.env" in r.json()["error"]["message"]


def test_relay_swaps_in_the_real_key_and_records_the_exchange(make_client, tmp_path):
    gateway = FakeGateway()
    c = make_client(authed=False, upstream=Upstream("https://gw.example/", REAL_KEY),
                    upstream_transport=httpx.MockTransport(gateway))
    run = active_run(c, tmp_path)
    body = {"model": "claude-opus-5-5", "max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]}
    r = c.post("/relay/tok-test/v1/messages", json=body,
               headers={"authorization": "Bearer sk-dummy", "anthropic-version": "2026-10-21"})
    assert r.status_code == 200 and r.json() == MESSAGE
    assert r.headers["x-litellm-call-id"] == "call-123"           # gateway headers reach the lesson too

    [sent] = gateway.requests
    assert str(sent.url) == "https://gw.example/v1/messages"
    assert sent.headers["authorization"] == f"Bearer {REAL_KEY}"   # dummy key replaced
    assert sent.headers["anthropic-version"] == "2026-10-21"

    req, resp = [e for e in run.events if e["type"].startswith("llm.")]
    assert req["type"] == "llm.request" and req["data"]["body"] == body and req["data"]["call"] == 1
    assert "authorization" not in req["data"]["headers"]
    assert resp["type"] == "llm.response" and resp["data"]["body"] == MESSAGE and resp["data"]["status"] == 200
    assert resp["data"]["cost_usd"] == 0.001408 and run.cost_usd == 0.001408
    assert REAL_KEY not in json.dumps(run.events)


def test_streams_pass_through_and_are_recorded_whole(make_client, tmp_path):
    c = make_client(authed=False, upstream=Upstream("https://gw.example", REAL_KEY),
                    upstream_transport=httpx.MockTransport(FakeGateway()))
    run = active_run(c, tmp_path)
    r = c.post("/relay/tok-test/v1/messages", json={"model": "claude-opus-5-5", "max_tokens": 64,
                                                     "messages": [{"role": "user", "content": "hi"}], "stream": True})
    assert r.status_code == 200 and r.text == SSE                  # byte-for-byte, as it streamed
    resp = next(e["data"] for e in run.events if e["type"] == "llm.response")
    assert resp["stream"] is True
    assert [e["event"] for e in resp["body"]["events"]] == ["message_start", "content_block_delta",
                                                             "message_delta", "message_stop"]
    assert resp["usage"] == {"input_tokens": 22, "output_tokens": 66} and resp["cost_usd"] == 0.001408


def test_parse_sse_and_stream_usage():
    events = parse_sse(SSE.replace("\n", "\r\n"))
    assert events[0] == {"event": "message_start",
                         "data": {"type": "message_start", "message": {"usage": {"input_tokens": 22, "output_tokens": 1}}}}
    assert stream_usage(events) == {"input_tokens": 22, "output_tokens": 66}
