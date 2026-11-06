"""Runner and relay end to end: a real server on a free port, real lesson processes using the
real SDK, and a fake gateway behind the relay. These prove stage 1's done-when:
the timeout kills the whole tree, lesson code never holds the real key, and every request
and response is recorded in order."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from conftest import TOKEN

from academy_server.app import AppSettings, create_app
from academy_server.relay import Upstream, parse_sse
from academy_server.runs import DUMMY_KEY
from academy_server.runs.proctree import pid_alive

REAL_KEY = "sk-real-gateway-key-must-never-reach-lesson-code"
MESSAGE = {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
           "content": [{"type": "text", "text": "An agent loop repeats until the task is done."}],
           "stop_reason": "end_turn", "stop_sequence": None,
           "usage": {"input_tokens": 22, "output_tokens": 66, "cache_creation_input_tokens": 0,
                     "cache_read_input_tokens": 0}}
SSE = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in [
    ("message_start", {"type": "message_start", "message": {
        "id": "msg_s", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
        "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 22, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}),
    ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
    ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello "}}),
    ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "stream"}}),
    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                       "usage": {"output_tokens": 66}}),
    ("message_stop", {"type": "message_stop"}),
])

STEPS = {   # step id -> (starter main.py, time limit in seconds)
    "call": ("""
import os
import anthropic
client = anthropic.Anthropic()
r = client.messages.create(model=os.environ["LAB_MODEL"], max_tokens=64, messages=[{"role": "user", "content": "hi"}])
print("answer:", r.content[0].text)
print("lesson key:", os.environ["ANTHROPIC_API_KEY"])
""", 120),
    "stream": ("""
import anthropic
with anthropic.Anthropic().messages.stream(model="claude-opus-5-5", max_tokens=64,
                                           messages=[{"role": "user", "content": "hi"}]) as s:
    print("streamed:", s.get_final_text())
""", 120),
    "env": ("""
import json, os
print(json.dumps({"keys": sorted(os.environ), "key": os.environ.get("ANTHROPIC_API_KEY"),
                  "url": os.environ.get("ANTHROPIC_BASE_URL")}))
""", 120),
    "hang": ("""
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path("child.pid").write_text(str(child.pid))
print("spawned", child.pid, flush=True)
time.sleep(120)
""", 5),
    "orphan": ("""
import pathlib, subprocess, sys
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path("child.pid").write_text(str(child.pid))
print("left behind", child.pid)
""", 120),
}


def write_content(root: Path) -> None:
    chapter = root / "mt-mod" / "lt-ch"
    chapter.mkdir(parents=True)
    (root / "mt-mod" / "module.yaml").write_text('id: mt\ntitle: "Test module"\nchapters: [lt-ch]\n', encoding="utf-8")
    (chapter / "chapter.yaml").write_text(f'id: lt\ntitle: "Test chapter"\nsteps: [{", ".join(STEPS)}]\n',
                                          encoding="utf-8")
    for name, (code, limit) in STEPS.items():
        (chapter / name / "starter").mkdir(parents=True)
        (chapter / name / "step.yaml").write_text(
            f'id: {name}\ntitle: "{name}"\nfiles:\n  main.py: starter/main.py\nrun:\n  timeout_s: {limit}\n', encoding="utf-8")
        (chapter / name / "step.md").write_text(f"# {name}\n", encoding="utf-8")
        (chapter / name / "starter" / "main.py").write_text(code.lstrip(), encoding="utf-8")


class FakeGateway:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if json.loads(request.content or b"{}").get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=SSE.encode())
        return httpx.Response(200, json=MESSAGE, headers={"x-litellm-call-id": "call-123"})


@pytest.fixture
def server(home, tmp_path, monkeypatch):
    monkeypatch.delenv("LAB_MODEL", raising=False)
    content = tmp_path / "content"
    write_content(content)
    gateway = FakeGateway()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings = AppSettings(token=TOKEN, port=port, content_dir=content, db_path=home / "academy.db",
                           web_dist=home / "no-web", upstream=Upstream("https://gateway.example", REAL_KEY),
                           upstream_transport=httpx.MockTransport(gateway), playground_root=tmp_path / "playground")
    srv = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not srv.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={"x-academy-token": TOKEN},
                          timeout=30, trust_env=False)
    yield SimpleNamespace(client=client, gateway=gateway, port=port, play=tmp_path / "playground")
    client.close()
    srv.should_exit = True
    thread.join(timeout=15)


def wait_finished(server, run_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view = server.client.get(f"/api/runs/{run_id}").json()
        if view["run"]["status"] == "finished":
            return view
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not finish in {timeout}s")


def run_to_end(server, step: str, timeout: float = 60) -> dict:
    r = server.client.post(f"/api/steps/mt.lt.{step}/runs", json={})
    assert r.status_code == 201, r.text
    return wait_finished(server, r.json()["run_id"], timeout)


def console(view: dict) -> list[str]:
    return [e["data"]["text"] for e in view["events"] if e["type"] in ("console.out", "console.err")]


def first(view: dict, type_: str) -> dict:
    return next(e["data"] for e in view["events"] if e["type"] == type_)


def assert_dead(pid: int, within: float = 5.0) -> None:
    deadline = time.monotonic() + within
    while pid_alive(pid):
        assert time.monotonic() < deadline, f"process {pid} is still running"
        time.sleep(0.1)


def read_sse(server, run_id: str, headers: dict | None = None) -> list[dict]:
    with server.client.stream("GET", f"/api/runs/{run_id}/events", headers=headers or {}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        frames = parse_sse(r.read().decode("utf-8"))
    assert frames[-1]["event"] == "end"
    return [f["data"] for f in frames if f["event"] is None]


def test_model_call_goes_through_the_relay_with_the_real_key(server):
    view = run_to_end(server, "call")
    assert view["run"]["outcome"] == "ok", console(view)

    [sent] = server.gateway.requests
    assert str(sent.url) == "https://gateway.example/v1/messages"
    assert sent.headers["authorization"] == f"Bearer {REAL_KEY}"

    events = view["events"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    types = [e["type"] for e in events]
    assert types[0] == "run.started" and types[-1] == "run.exit"
    i_request, i_response = types.index("llm.request"), types.index("llm.response")
    i_answer = next(i for i, e in enumerate(events)
                    if e["type"] == "console.out" and e["data"]["text"].startswith("answer:"))
    assert i_request < i_response < i_answer          # the order things actually happened

    request, response = events[i_request]["data"], events[i_response]["data"]
    assert request["body"] == {"max_tokens": 64, "messages": [{"role": "user", "content": "hi"}],
                               "model": "claude-opus-5-5"}
    assert "authorization" not in request["headers"]
    assert response["status"] == 200 and response["body"] == MESSAGE
    assert response["cost_usd"] == 0.001408 and response["headers"]["x-litellm-call-id"] == "call-123"

    assert f"lesson key: {DUMMY_KEY}" in console(view)
    assert REAL_KEY not in json.dumps(view)

    [saved] = server.client.get("/api/steps/mt.lt.call/runs").json()["runs"]
    assert saved["outcome"] == "ok" and saved["cost_usd"] == 0.001408
    assert server.client.get("/api/status").json()["store"]["spend"]["today_usd"] == 0.001408


def test_streamed_call_passes_through_and_is_recorded(server):
    view = run_to_end(server, "stream")
    assert view["run"]["outcome"] == "ok", console(view)
    assert "streamed: Hello stream" in console(view)
    response = first(view, "llm.response")
    assert response["stream"] is True and response["body"]["events"][0]["event"] == "message_start"
    assert response["usage"]["input_tokens"] == 22 and response["usage"]["output_tokens"] == 66
    assert response["cost_usd"] == 0.001408


def test_lesson_environment_is_allowlisted(server, monkeypatch):
    monkeypatch.setenv("FDE_TEST_SECRET", "leak-me")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "leak-me-too")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    view = run_to_end(server, "env")
    seen = json.loads(next(line for line in console(view) if line.startswith("{")))
    assert not {"FDE_TEST_SECRET", "ANTHROPIC_AUTH_TOKEN", "HTTPS_PROXY"} & set(seen["keys"])
    assert seen["key"] == DUMMY_KEY
    assert seen["url"].startswith(f"http://127.0.0.1:{server.port}/relay/")


def test_timeout_kills_the_whole_process_tree(server):
    view = run_to_end(server, "hang", timeout=30)
    assert view["run"]["outcome"] == "timeout"
    started = first(view, "run.started")
    if sys.platform == "win32":
        assert started["job_object"] is True
    child = int((server.play / "mt.lt.hang" / "child.pid").read_text())
    assert_dead(started["pid"])
    assert_dead(child)


def test_processes_left_behind_die_when_the_run_ends(server):
    view = run_to_end(server, "orphan")
    assert view["run"]["outcome"] == "ok"
    assert_dead(int((server.play / "mt.lt.orphan" / "child.pid").read_text()))


def test_one_run_at_a_time_and_stop(server):
    first_run = server.client.post("/api/steps/mt.lt.hang/runs", json={})
    assert first_run.status_code == 201
    assert server.client.post("/api/steps/mt.lt.call/runs", json={}).status_code == 409
    run_id = first_run.json()["run_id"]
    assert server.client.post(f"/api/runs/{run_id}/stop").status_code == 200
    assert wait_finished(server, run_id)["run"]["outcome"] == "stopped"


def test_event_stream_is_live_ordered_and_resumable(server):
    run_id = server.client.post("/api/steps/mt.lt.call/runs", json={}).json()["run_id"]
    live = read_sse(server, run_id)            # opened while the run is still going
    view = wait_finished(server, run_id)
    assert live == view["events"] and live[-1]["type"] == "run.exit"
    n = len(live)
    assert [e["seq"] for e in read_sse(server, run_id, {"last-event-id": str(n - 2)})] == [n - 1, n]


def test_run_uses_the_code_saved_from_the_editor(server):
    base = server.client.get("/api/steps/mt.lt.env/files").json()["files"]["main.py"]["hash"]
    saved = server.client.put("/api/steps/mt.lt.env/files/main.py",
                              json={"code": 'print("edited in the browser")\n', "base_hash": base})
    assert saved.status_code == 200
    assert console(run_to_end(server, "env")) == ["edited in the browser"]


def test_finished_runs_reopen_from_the_store(server, make_client):
    view = run_to_end(server, "call")
    fresh = make_client()                       # a new app on the same database: nothing in memory
    reopened = fresh.get(f"/api/runs/{view['run']['run_id']}").json()
    assert reopened["run"]["status"] == "finished" and reopened["run"]["outcome"] == "ok"
    assert reopened["events"] == view["events"]
