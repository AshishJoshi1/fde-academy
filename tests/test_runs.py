"""Runner and relay end to end: a real server on a free port, real lesson processes using the
real SDK, and a fake gateway behind the relay. These prove stage 1's done-when:
the timeout kills the whole tree, lesson code never holds the real key, and every request
and response is recorded in order."""
from __future__ import annotations

import json
import re
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
from academy_server.experiments import run_facts
from academy_server.relay import Upstream, parse_sse
from academy_server.runs import DUMMY_KEY
from academy_server.runs.proctree import pid_alive

REAL_KEY = "sk-real-gateway-key-must-never-reach-lesson-code"
LAB02 = Path(__file__).resolve().parent.parent / "content" / "m02-agent-loop" / "lab02-agent-loop"
S02_STARTER = LAB02 / "s02-manual-loop" / "starter" / "main.py"
S03_STARTER = (LAB02 / "s03-parallel-tools" / "starter" / "main.py").read_text(encoding="utf-8")
S03_PARALLEL_OFF = '        # tool_choice={"type": "auto", "disable_parallel_tool_use": True},  # E1'
assert S03_PARALLEL_OFF in S03_STARTER and S03_STARTER.count("OPP-1046") == 1   # what E1 and E2 change
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
    "loop": (S02_STARTER.read_text(encoding="utf-8"), 120),    # the real s02 code, against the real mock API
    "parallel": (S03_STARTER, 120),                             # the real s03 code, as it starts
    "sequential": (S03_STARTER.replace(S03_PARALLEL_OFF, S03_PARALLEL_OFF.replace("# ", "", 1)), 120),   # E1's change
    "missing": (S03_STARTER.replace("OPP-1046", "OPP-1099"), 120),                                      # E2's change
    "orphan": ("""
import pathlib, subprocess, sys
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path("child.pid").write_text(str(child.pid))
print("left behind", child.pid)
""", 120),
}


EXPERIMENT = """experiments:
  - id: e1
    title: "Count the calls"
    question: "How many calls?"
    change: "Nothing."
    explain: "One call."
    predict:
      - {id: p1, type: numeric, prompt: "Calls?", answer_from: run.calls}
      - {id: p2, type: mcq, prompt: "stop_reason?", options: [end_turn, max_tokens], answer_from: response.stop_reason}
"""


def write_content(root: Path) -> None:
    chapter = root / "mt-mod" / "lt-ch"
    chapter.mkdir(parents=True)
    (root / "mt-mod" / "module.yaml").write_text('id: mt\ntitle: "Test module"\nchapters: [lt-ch]\n', encoding="utf-8")
    (chapter / "chapter.yaml").write_text(f'id: lt\ntitle: "Test chapter"\nsteps: [{", ".join(STEPS)}]\n',
                                          encoding="utf-8")
    for name, (code, limit) in STEPS.items():
        (chapter / name / "starter").mkdir(parents=True)
        (chapter / name / "step.yaml").write_text(
            f'id: {name}\ntitle: "{name}"\nfiles:\n  main.py: starter/main.py\nrun:\n  timeout_s: {limit}\n'
            + ("  fixture: meridian\n" if name in ("loop", "parallel", "sequential", "missing") else "")
            + (EXPERIMENT if name == "call" else ""), encoding="utf-8")
        (chapter / name / "step.md").write_text(f"# {name}\n", encoding="utf-8")
        (chapter / name / "starter" / "main.py").write_text(code.lstrip(), encoding="utf-8")


class FakeGateway:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = json.loads(request.content or b"{}")
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=SSE.encode())
        # With tools: one get_opportunity per OPP- ID in the question, all in one turn (parallel calls),
        # or one per turn under disable_parallel_tool_use; then a text answer.
        messages = body.get("messages") or [{}]
        question = messages[0].get("content")
        wanted = re.findall(r"OPP-\d+", question if isinstance(question, str) else "")
        uses = [b for m in messages if m.get("role") == "assistant" and isinstance(m.get("content"), list)
                for b in m["content"] if b.get("type") == "tool_use"]
        todo = [x for x in wanted if x not in {b["input"]["opportunity_id"] for b in uses}]
        if body.get("tools") and todo:
            if (body.get("tool_choice") or {}).get("disable_parallel_tool_use"):
                todo = todo[:1]
            return httpx.Response(200, json={**MESSAGE, "stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": f"toolu_test{len(uses) + k + 1}", "name": "get_opportunity",
                 "input": {"opportunity_id": opp}} for k, opp in enumerate(todo)]})
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
    assert not {"MERIDIAN_API_URL", "MERIDIAN_API_TOKEN"} & set(seen["keys"])   # only a step with the fixture


def test_a_fixture_step_runs_the_loop_against_the_mock_api(server):
    view = run_to_end(server, "loop")
    assert view["run"]["outcome"] == "ok", console(view)
    events = view["events"]
    started = first(view, "run.started")
    assert started["fixture"]["name"] == "meridian" and started["fixture"]["url"].startswith("http://127.0.0.1:")
    # The order things happened: call 1 asks for the tool, the tool's API request, call 2 carries its result.
    order = [(e["type"], e["data"].get("call")) for e in events
             if e["type"] in ("llm.request", "llm.response", "api.request")]
    assert order == [("llm.request", 1), ("llm.response", 1), ("api.request", None),
                     ("llm.request", 2), ("llm.response", 2)]
    api = first(view, "api.request")
    assert (api["n"], api["fixture"], api["method"], api["path"], api["status"]) == \
        (1, "meridian", "GET", "/opportunities/OPP-1042", 200)
    assert api["body"]["opportunity_id"] == "OPP-1042" and api["body"]["account_id"] == "ACC-017"
    second = [e["data"]["body"] for e in events if e["type"] == "llm.request"][1]
    result = second["messages"][2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_test1"
    assert json.loads(result["content"]) == api["body"]          # what the API sent is what the model got
    facts = run_facts(events)
    assert facts["api.requests"] == 1 and facts["api.last_request"] == "GET /opportunities/OPP-1042 → 200"
    assert facts["first.response.stop_reason"] == "tool_use" and facts["response.stop_reason"] == "end_turn"
    assert facts["request.messages"] == 3 and facts["request.last_message"] == "user: tool_result"
    assert facts["request.history_grows"] is True and facts["request.tool_names"] == "get_opportunity"
    assert any(line.startswith("answer:") for line in console(view))
    with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):   # the mock API stopped with the run
        httpx.get(started["fixture"]["url"] + "/accounts", timeout=2, trust_env=False)


def _tool_results(request_body: dict) -> list[dict]:
    return [b for m in request_body["messages"] if isinstance(m["content"], list)
            for b in m["content"] if b.get("type") == "tool_result"]


def test_s03_parallel_calls_go_back_in_one_message(server):
    view = run_to_end(server, "parallel")
    assert view["run"]["outcome"] == "ok", console(view)
    events = view["events"]
    bodies = [e["data"]["body"] for e in events if e["type"] == "llm.request"]
    assert len(bodies) == 2                                    # one call asks for all three, one answers
    paths = [e["data"]["path"] for e in events if e["type"] == "api.request"]
    assert paths == ["/opportunities/OPP-1042", "/opportunities/OPP-1046", "/opportunities/OPP-1048"]
    last = bodies[1]["messages"][-1]
    assert last["role"] == "user" and [b["tool_use_id"] for b in last["content"]] == ["toolu_test1", "toolu_test2", "toolu_test3"]
    facts = run_facts(events)
    assert facts["first.response.tool_uses"] == 3 and facts["loop.tool_results"] == 3 and facts["loop.error_results"] == 0
    assert facts["first.response.tool_inputs"] == ('{"opportunity_id": "OPP-1042"}, {"opportunity_id": "OPP-1046"}, '
                                                   '{"opportunity_id": "OPP-1048"}')
    assert facts["request.last_message"] == "user: tool_result, tool_result, tool_result"
    assert facts["loop.results_in_one_message"] is True
    assert facts["run.input_tokens"] == 44                    # the fake gateway's 22 per call, added up


def test_s03_parallel_off_takes_a_call_per_lookup(server):
    parallel = run_to_end(server, "parallel")["events"]
    view = run_to_end(server, "sequential")
    assert view["run"]["outcome"] == "ok", console(view)
    bodies = [e["data"]["body"] for e in view["events"] if e["type"] == "llm.request"]
    assert [b["tool_choice"] for b in bodies] == [{"type": "auto", "disable_parallel_tool_use": True}] * 4
    facts = run_facts(view["events"], prev_events=parallel)
    assert facts["run.calls"] == 4 and facts["first.response.tool_uses"] == 1 and facts["request.messages"] == 7
    assert facts["loop.results_in_one_message"] is True and facts["loop.tool_results"] == 3
    assert facts["prev.run.input_tokens"] == 44 and facts["ratio.input_tokens"] == 2.0   # 4 calls against 2


def test_s03_a_failed_lookup_goes_back_as_is_error(server):
    view = run_to_end(server, "missing")
    assert view["run"]["outcome"] == "ok", console(view)
    events = view["events"]
    statuses = {e["data"]["path"]: e["data"]["status"] for e in events if e["type"] == "api.request"}
    assert statuses == {"/opportunities/OPP-1042": 200, "/opportunities/OPP-1099": 404, "/opportunities/OPP-1048": 200}
    results = _tool_results([e["data"]["body"] for e in events if e["type"] == "llm.request"][-1])
    failed = [r for r in results if r.get("is_error")]
    assert len(results) == 3 and len(failed) == 1
    assert failed[0]["content"] == "LookupError: no opportunity with ID OPP-1099"     # no URL, no token
    facts = run_facts(events)
    assert facts["loop.error_results"] == 1 and facts["loop.results_in_one_message"] is True
    assert any("-> is_error" in line for line in console(view))


def test_results_in_one_message_catches_split_and_missing_results():
    from academy_server.experiments import results_in_one_message
    ask = {"role": "assistant", "content": [{"type": "tool_use", "id": "a"}, {"type": "tool_use", "id": "b"}]}
    res = {"a": {"type": "tool_result", "tool_use_id": "a"}, "b": {"type": "tool_result", "tool_use_id": "b"}}
    q = {"role": "user", "content": "q"}
    assert results_in_one_message([q]) is None                                          # no tool asked for
    assert results_in_one_message([q, ask, {"role": "user", "content": [res["b"], res["a"]]}]) is True  # any order
    assert results_in_one_message([q, ask, {"role": "user", "content": [res["a"]]},
                                   {"role": "user", "content": [res["b"]]}]) is False   # split: the API accepts it
    assert results_in_one_message([q, ask, {"role": "user", "content": [res["a"]]}]) is False   # one missing
    assert results_in_one_message([q, ask]) is False                                     # dropped (s02's E2: a 400)


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


def test_a_run_started_for_an_experiment_grades_its_predictions(server):
    url = "/api/steps/mt.lt.call/experiments/e1"
    assert server.client.post("/api/steps/mt.lt.call/runs", json={"experiment": "e1"}).status_code == 409
    assert server.client.post(f"{url}/predictions", json={"answers": {"p1": 1, "p2": 1}}).status_code == 200
    started = server.client.post("/api/steps/mt.lt.call/runs", json={"experiment": "e1"})
    assert started.status_code == 201 and started.json()["experiment"] == "e1"
    wait_finished(server, started.json()["run_id"])
    state = server.client.post(f"{url}/grade").json()
    assert state["status"] == "graded" and state["attempt"]["run_id"] == started.json()["run_id"]
    assert {p["item_id"]: p["correct"] for p in state["attempt"]["predictions"]} == {"p1": True, "p2": False}
    assert server.client.post("/api/steps/mt.lt.call/runs", json={"experiment": "e1"}).status_code == 409
    [run] = server.client.get("/api/steps/mt.lt.call/runs").json()["runs"]
    assert run["experiment_id"] == "e1" and run["attempt"] == 1
