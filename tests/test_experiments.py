"""Experiments: facts measured from a run, prediction grading, the code diff, the store, and the
lab API for cards and the quiz. The API tests use the real s01 cards, graded against runs written
straight into the store, plus a fake gateway for count_tokens: no lesson process needed."""
from __future__ import annotations

import json
import shutil
import sqlite3

import httpx
import pytest
from conftest import REPO

from academy_server.content.loader import load_content
from academy_server.content.schema import FACTS, Experiment, PredictMCQ, PredictNumeric, PredictText
from academy_server.experiments import code_diff, error_message, grade, run_facts
from academy_server.relay import Upstream
from academy_server.store import Store
from academy_server.store.migrations import MIGRATIONS

STEP = "m02.lab02.s01"
PROMPT = "In one sentence: what is an agent loop?"
LOW = {"type": "message", "role": "assistant", "model": "claude-opus-5-5", "stop_reason": "end_turn",
       "content": [{"type": "text", "text": "An agent loop is the repeating cycle in which a model acts."}],
       "usage": {"input_tokens": 22, "output_tokens": 65, "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": 0}}
HIGH = {**LOW, "content": [{"type": "thinking", "thinking": "", "signature": "sig"}, LOW["content"][0]],
        "usage": {**LOW["usage"], "output_tokens": 84}}
CUT = {**LOW, "stop_reason": "max_tokens", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                                       {"type": "text", "text": "An agent loop is the rep"}],
       "usage": {**LOW["usage"], "output_tokens": 20}}
GATEWAY_400 = {"error": {"message": '{"type":"error","error":{"type":"invalid_request_error","message":'
                                    '"This model does not support the effort parameter."},"request_id":"req_1"}'
                                    "No fallback model group found for original model_group=claude-haiku-4-5.",
                         "type": None, "param": None, "code": "400"}}


def events(body, *, status=200, effort="low", max_tokens=1024, model="claude-opus-5-5", cost=0.001388,
           gateway_cost="0.0013880000000000001", calls=1):
    """A run's events, shaped like the runner and relay record them."""
    out = [{"seq": 1, "t_ms": 0, "type": "run.started", "data": {"model": model, "entry": "main.py", "timeout_s": 120}}]
    request = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": PROMPT}]}
    if effort:
        request["output_config"] = {"effort": effort}
    for n in range(1, calls + 1):
        out.append({"seq": len(out) + 1, "t_ms": 2900, "type": "llm.request",
                    "data": {"call": n, "method": "POST", "path": "/v1/messages", "body": request,
                             "headers": {"x-stainless-retry-count": str(n - 1)}}})
        out.append({"seq": len(out) + 1, "t_ms": 4100, "type": "llm.response",
                    "data": {"call": n, "status": status, "stream": False, "ms": 1200, "body": body,
                             "usage": body.get("usage") if status < 400 else None,
                             "cost_usd": cost if status < 400 else None,
                             "headers": {"x-litellm-response-cost-original": gateway_cost} if status < 400 else {}}})
    out.append({"seq": len(out) + 1, "t_ms": 4200, "type": "run.exit",
                "data": {"outcome": "ok" if status < 400 else "error", "exit_code": 0 if status < 400 else 1}})
    return out


# ------------------------------------------------------------------- facts
def test_run_facts_measures_every_fact_key():
    facts = run_facts(events(HIGH, effort="high"), events(LOW), text_tokens=12)
    assert set(facts) == set(FACTS)
    assert facts["run.outcome"] == "ok" and facts["run.calls"] == 1 and facts["run.first_call_ms"] == 2900
    assert facts["request.effort"] == "high" and facts["request.retry_count"] == 0
    assert facts["response.blocks"] == "thinking, text" and facts["response.has_thinking"] is True
    assert facts["response.thinking_text"] == "empty" and facts["response.has_text"] is True
    assert facts["response.usage.output_tokens"] == 84 and facts["response.hidden_output_tokens"] == 72
    assert facts["response.cost_matches_gateway"] is True       # float noise in the header still matches
    assert facts["prev.response.usage.output_tokens"] == 65 and facts["ratio.output_tokens"] == 1.292


def test_facts_from_a_streamed_response():
    sse = [{"event": "message_start", "data": {"type": "message_start", "message": {
               "type": "message", "role": "assistant", "content": [], "stop_reason": None}}},
           {"event": "content_block_start", "data": {"type": "content_block_start", "index": 0,
                                                      "content_block": {"type": "text", "text": ""}}},
           {"event": "content_block_delta", "data": {"type": "content_block_delta", "index": 0,
                                                      "delta": {"type": "text_delta", "text": "Hello "}}},
           {"event": "content_block_delta", "data": {"type": "content_block_delta", "index": 0,
                                                      "delta": {"type": "text_delta", "text": "stream"}}},
           {"event": "message_delta", "data": {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}}]
    evs = events({"events": sse})
    evs[2]["data"]["usage"] = {"input_tokens": 22, "output_tokens": 66}
    facts = run_facts(evs)
    assert facts["response.stop_reason"] == "end_turn" and facts["response.blocks"] == "text"
    assert facts["response.text_chars"] == len("Hello stream") and facts["response.usage.output_tokens"] == 66


def test_gateway_error_is_unwrapped():
    facts = run_facts(events(GATEWAY_400, status=400, model="claude-haiku-4-5"))
    assert facts["response.status"] == 400 and facts["run.outcome"] == "error"
    assert facts["response.error_message"] == "This model does not support the effort parameter."
    assert facts["response.stop_reason"] is None and facts["response.usage.output_tokens"] is None
    assert error_message({"type": "error", "error": {"type": "x", "message": "plain"}}) == "plain"


def test_a_run_without_model_calls_measures_nothing():
    facts = run_facts([{"seq": 1, "t_ms": 0, "type": "run.started", "data": {"model": "m"}},
                       {"seq": 2, "t_ms": 9, "type": "run.exit", "data": {"outcome": "error", "exit_code": 1}}])
    assert facts["run.calls"] == 0 and facts["run.first_call_ms"] is None and facts["response.status"] is None


# ----------------------------------------------------------------- grading
def mcq(**kw):
    return PredictMCQ(id="p", type="mcq", prompt="?", **kw)


def test_mcq_against_a_measured_value():
    facts = run_facts(events(HIGH, effort="high"), events(LOW))
    blocks = mcq(options=[{"label": "Only text", "value": "text"}, {"label": "Thinking, then text",
                                                                     "value": "thinking, text"}],
                 answer_from="response.blocks")
    assert grade(blocks, 1, facts)["correct"] is True
    assert grade(blocks, 0, facts)["correct"] is False
    yes_no = mcq(options=["yes", "no"], answer_from="response.has_thinking")   # booleans match yes / no
    assert grade(yes_no, 0, facts)["correct"] is True
    binned = mcq(options=["under 1.5x", "1.5x to 4x", "4x or more"], bins=[1.5, 4], answer_from="ratio.output_tokens")
    g = grade(binned, 0, facts)
    assert g["correct"] is True and g["actual_display"] == "under 1.5x (ratio.output_tokens = 1.292)"
    status = mcq(options=[{"label": "200 OK", "value": 200}, {"label": "400", "value": 400}],
                 answer_from="response.status")
    assert grade(status, 1, run_facts(events(GATEWAY_400, status=400)))["correct"] is True


def test_mcq_with_no_matching_option_is_a_surprise_and_unmeasured_is_ungraded():
    facts = run_facts(events(LOW))
    stop = mcq(options=["max_tokens", "tool_use"], answer_from="response.stop_reason")
    g = grade(stop, 0, facts)
    assert g["correct"] is False and "end_turn" in g["note"]
    errored = run_facts(events(GATEWAY_400, status=400))
    assert grade(stop, 0, errored)["correct"] is None          # no response, so no stop_reason to grade
    fixed = mcq(options=["a", "b"], answer=1)
    assert grade(fixed, 1, facts)["correct"] is True and grade(fixed, 0, facts)["actual_display"] == "b"


def test_numeric_tolerances():
    facts = run_facts(events(LOW))   # output_tokens 65, first call at 2900 ms
    def num(**kw):
        return PredictNumeric(id="p", type="numeric", prompt="?", **kw)
    exact = num(answer_from="response.usage.output_tokens")
    assert grade(exact, 65, facts)["correct"] is True and grade(exact, 64, facts)["correct"] is False
    factor = num(answer_from="run.first_call_ms", tol_factor=2)
    assert grade(factor, 1500, facts)["correct"] is True and grade(factor, 1400, facts)["correct"] is False
    assert grade(factor, 5800, facts)["correct"] is True and grade(factor, 6000, facts)["correct"] is False
    pct = num(answer_from="response.usage.output_tokens", tol_pct=10)
    assert grade(pct, 71, facts)["correct"] is True and grade(pct, 72, facts)["correct"] is False
    assert grade(num(answer_from="response.text_tokens"), 10, facts)["correct"] is None   # not counted


def test_text_predictions_are_shown_not_graded():
    item = PredictText(id="p", type="text", prompt="why?", show_from="response.blocks")
    g = grade(item, "hidden thinking", run_facts(events(HIGH)))
    assert g["correct"] is None and g["actual_display"] == "thinking, text"


@pytest.mark.parametrize("bad, message", [
    ({"options": ["a", "b"], "answer_from": "response.typo"}, "unknown fact"),
    ({"options": ["a", "b"], "answer": 0, "answer_from": "response.status"}, "exactly one"),
    ({"options": ["a", "b"], "answer_from": "response.status", "bins": [1, 2]}, "bins"),
    ({"options": ["a", "b"], "answer": 0, "bins": [1]}, "bins"),
    ({"options": ["a", "b"], "answer": 5}, "out of range"),
])
def test_schema_rejects_bad_predictions(bad, message):
    with pytest.raises(ValueError, match=message):
        Experiment.model_validate({"id": "e1", "title": "t", "question": "q", "change": "c", "explain": "x",
                                   "predict": [{"id": "p1", "type": "mcq", "prompt": "?", **bad}]})


def test_public_cards_hide_answers_and_explanations():
    step = load_content(REPO / "content").steps[STEP]
    pub = step.public()
    assert [e["id"] for e in pub["experiments"]] == ["e2", "e3", "e4", "e5"]
    for card in pub["experiments"]:
        assert "explain" not in card
        assert all("answer" not in p and "explanation" not in p for p in card["predict"])
    guide = step.spec.guide
    assert [g.id for g in guide] == [f"g{i}" for i in range(1, 10)]
    assert all(c.public().keys().isdisjoint({"answer", "explanation"}) for g in guide for c in g.check)
    assert guide[0].lines() == list(range(5, 14)) and guide[1].lines() == [16, 19]


@pytest.mark.parametrize("change, message", [
    ({"experiment": "e9"}, "unknown experiments"),
    ({"code": ["13-8"]}, "bad code line"),
    ({"show": ["response.typo"]}, "unknown fact"),
])
def test_schema_rejects_bad_guide_steps(change, message):
    from academy_server.content.schema import Step
    spec = load_content(REPO / "content").steps[STEP].spec.model_dump()
    spec["guide"][0].update(change)
    with pytest.raises(ValueError, match=message):
        Step.model_validate(spec)


def test_code_diff():
    assert code_diff({"main.py": "a\nb\n"}, {"main.py": "a\nb\n"}) == ""
    diff = code_diff({"main.py": 'effort = "low"\n'}, {"main.py": 'effort = "high"\n'})
    assert '-effort = "low"' in diff and '+effort = "high"' in diff and "previous run/main.py" in diff


# ------------------------------------------------------------------- store
def record_run(store, run_id, evs, *, code='x = 1\n', model="claude-opus-5-5"):
    store.record_run_start(run_id, STEP, "m02", "live", model, {"main.py": code})
    store.save_run_events(run_id, evs)
    store.record_run_end(run_id, evs[-1]["data"]["outcome"], 0.0)


def test_attempt_lifecycle(store):
    items = [{"item_id": "p1", "type": "mcq", "prompt": "?", "answer": 0}]
    a = store.commit_predictions(STEP, "m02", "e1", items)
    assert a["attempt"] == 1 and a["run_id"] is None and a["predictions"][0]["answer"] == 0
    with pytest.raises(ValueError, match="already committed"):
        store.commit_predictions(STEP, "m02", "e1", items)
    record_run(store, "r1", events(LOW))
    assert store.attach_run(a["id"], "r1") is True
    assert store.attach_run(a["id"], "r2") is False                    # one run per attempt
    assert store.save_explanation(a["id"], "too early") is False       # explain only after grading
    store.save_grades(a["id"], {"p1": {"correct": False, "actual": "x", "actual_display": "x", "note": ""}})
    assert store.save_explanation(a["id"], "because") is True
    again = store.commit_predictions(STEP, "m02", "e1", items)          # a redo is a new attempt
    assert again["attempt"] == 2
    assert [x["attempt"] for x in store.attempts(STEP, "e1")] == [1, 2]
    assert store.prediction_stats() == {"graded": 1, "right": 0, "surprises": 1, "explained": 1, "cards_done": 1}
    assert [s["item_id"] for s in store.surprises()] == ["p1"]


def test_run_code_and_previous_run(store):
    record_run(store, "20261109-100000-aaaaaa", events(LOW), code="v1\n")
    record_run(store, "20261109-100100-bbbbbb", events(LOW), code="v2\n")
    assert store.run_code("20261109-100100-bbbbbb") == {"main.py": "v2\n"}
    assert store.previous_run("20261109-100100-bbbbbb")["run_id"] == "20261109-100000-aaaaaa"
    assert store.previous_run("20261109-100000-aaaaaa") is None


def test_migration_links_old_run_snapshots_to_their_runs(home):
    path = home / "old.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as c:              # a database from before migration 3
        for version, sql in enumerate(MIGRATIONS[:2], start=1):
            c.executescript(f"{sql}\nPRAGMA user_version = {version};")
        c.execute("INSERT INTO runs (run_id, step_id, module_id, mode, started_at) VALUES "
                  "('r-old', ?, 'm02', 'live', '2026-11-07T10:00:00.000+00:00')", (STEP,))
        c.execute("INSERT INTO code_snapshots (step_id, kind, filename, code, created_at) VALUES "
                  "(?, 'run', 'main.py', 'old code', '2026-11-07T10:00:00.004+00:00')", (STEP,))
    store = Store(path)
    assert store.run_code("r-old") == {"main.py": "old code"}
    store.close()


def test_export_import_keeps_predictions(store, home):
    record_run(store, "r1", events(LOW))
    a = store.commit_predictions(STEP, "m02", "e1", [{"item_id": "p1", "type": "numeric", "answer": 60.0}])
    store.attach_run(a["id"], "r1")
    store.save_grades(a["id"], {"p1": {"correct": True, "actual": 65, "actual_display": "65", "note": ""}})
    exported = store.export_all()
    fresh = Store(home / "fresh.db")
    assert fresh.import_all(exported)["predictions"] == 1
    assert fresh.attempts(STEP, "e1")[0]["predictions"][0]["correct"] is True
    assert fresh.export_all()["tables"] == exported["tables"]
    fresh.close()


# --------------------------------------------------------------------- API
class CountGateway:
    """Fake gateway for count_tokens: a message costs 8 tokens plus one per word."""
    def __init__(self):
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages/count_tokens"
        assert request.headers["authorization"] == "Bearer sk-real" and request.headers["anthropic-version"]
        self.calls += 1
        text = json.loads(request.content)["messages"][0]["content"]
        return httpx.Response(200, json={"input_tokens": 8 + len(text.split())})


@pytest.fixture
def lab(make_client, store):
    gateway = CountGateway()
    client = make_client(upstream=Upstream("https://gw.example", "sk-real"),
                         upstream_transport=httpx.MockTransport(gateway))
    return client, client.app.state.store, gateway


def commit(client, exp, answers):
    return client.post(f"/api/steps/{STEP}/experiments/{exp}/predictions", json={"answers": answers})


def graded_against(client, store, exp, evs, run_id, code="x = 1\n", model="claude-opus-5-5"):
    """Attach a recorded run to the latest attempt, the way POST /runs does, then compare."""
    record_run(store, run_id, evs, code=code, model=model)
    store.attach_run(store.attempts(STEP, exp)[-1]["id"], run_id)
    r = client.post(f"/api/steps/{STEP}/experiments/{exp}/grade")
    assert r.status_code == 200, r.text
    return r.json()


def verdicts(state):
    return {p["item_id"]: p["correct"] for p in state["attempt"]["predictions"]}


def test_card_flow_predict_compare_explain(lab):
    client, store, _ = lab
    states = client.get(f"/api/steps/{STEP}/experiments").json()["experiments"]
    assert [s["status"] for s in states] == ["predict"] * 4 and states[0]["explain"] is None

    graded_run = client.post(f"/api/steps/{STEP}/runs", json={"experiment": "e2"})
    assert graded_run.status_code == 409 and "commit your predictions" in graded_run.json()["detail"]
    assert commit(client, "e2", {"p1": 0}).status_code == 400                 # every prediction needs an answer
    assert commit(client, "e2", {"p1": 9, "p2": 0, "p3": 0}).status_code == 400

    answers = {"p1": 0, "p2": 1, "p3": 0}
    state = commit(client, "e2", answers).json()
    assert state["status"] == "committed" and state["attempt"]["attempt"] == 1
    assert commit(client, "e2", answers).status_code == 409                   # locked in until the run

    record_run(store, "20261109-100000-aaaaaa", events(LOW))
    state = graded_against(client, store, "e2", events(HIGH, effort="high"), "20261109-100100-bbbbbb")
    assert state["status"] == "graded"
    assert verdicts(state) == {"p1": True, "p2": True, "p3": True}
    assert state["explain"] is None                                           # your why comes first

    assert client.post(f"/api/steps/{STEP}/experiments/e2/explain", json={"text": ""}).status_code == 422
    done = client.post(f"/api/steps/{STEP}/experiments/e2/explain", json={"text": "It barely thought"}).json()
    assert done["status"] == "explained" and '"omitted"' in done["explain"]
    assert done["attempt"]["explanation"] == "It barely thought"

    redo = commit(client, "e2", answers).json()                              # redo: earlier attempt kept beside
    assert redo["attempt"]["attempt"] == 2 and [a["attempt"] for a in redo["earlier"]] == [1]


def test_effort_card_compares_with_the_previous_run(lab):
    client, store, _ = lab
    record_run(store, "20261109-100000-aaaaaa", events(LOW), code='effort = "low"\n')
    commit(client, "e2", {"p1": 0, "p2": 1, "p3": 2})
    state = graded_against(client, store, "e2", events(HIGH, effort="high"), "20261109-100100-bbbbbb",
                           code='effort = "high"\n')
    assert verdicts(state) == {"p1": True, "p2": True, "p3": False}           # x1.3, not x4
    diff = client.get("/api/runs/20261109-100100-bbbbbb/diff").json()
    assert diff["prev_run_id"] == "20261109-100000-aaaaaa"
    assert '+effort = "high"' in diff["diff"] and diff["model"] == {"prev": "claude-opus-5-5", "now": "claude-opus-5-5"}


def test_token_cards_measure_the_text_with_count_tokens(lab):
    client, store, gateway = lab
    commit(client, "e4", {"p1": 1, "p2": 20, "p3": 0, "p4": 6})
    state = graded_against(client, store, "e4", events(CUT, max_tokens=20), "20261109-100000-aaaaaa")
    by_id = {p["item_id"]: p for p in state["attempt"]["predictions"]}
    assert verdicts(state) == {"p1": True, "p2": True, "p3": True, "p4": True}
    assert by_id["p4"]["actual"] == 6                     # "An agent loop is the rep": 6 words in the fake
    assert gateway.calls == 2                             # the wrapper ("a"), then the answer


def test_model_card_grades_the_400(lab):
    client, store, _ = lab
    commit(client, "e5", {"p1": 1, "p2": 3, "p3": "effort not supported"})
    state = graded_against(client, store, "e5", events(GATEWAY_400, status=400, model="claude-haiku-4-5"),
                           "20261109-100000-aaaaaa", model="claude-haiku-4-5")
    by_id = {p["item_id"]: p for p in state["attempt"]["predictions"]}
    assert verdicts(state) == {"p1": True, "p2": False, "p3": None}           # 4xx: one request, no retries
    assert by_id["p3"]["actual_display"] == "This model does not support the effort parameter."


def test_first_run_diff_says_so(lab):
    client, store, _ = lab
    record_run(store, "20261109-100000-aaaaaa", events(LOW))
    view = client.get("/api/runs/20261109-100000-aaaaaa/diff").json()
    assert view["prev_run_id"] is None and "first run" in view["note"] and view["code"] == {"main.py": "x = 1\n"}
    assert client.get("/api/runs/nope/diff").status_code == 404


def test_quiz_answers_are_graded_and_recorded(lab):
    client, store, _ = lab
    wrong = client.post(f"/api/steps/{STEP}/quiz/q1", json={"answer": 0}).json()
    assert wrong["correct"] is False and wrong["correct_answer"] == 1 and "thinking" in wrong["explanation"]
    assert [m["item_id"] for m in store.mistakes("m02")["still_wrong"]] == [f"{STEP}:q1"]
    right = client.post(f"/api/steps/{STEP}/quiz/q1", json={"answer": 1}).json()
    assert right["correct"] is True
    assert [m["item_id"] for m in store.mistakes("m02")["fixed_after_retry"]] == [f"{STEP}:q1"]
    assert client.post(f"/api/steps/{STEP}/quiz/q2", json={"answer": 0.002525}).json()["correct"] is True
    assert client.post(f"/api/steps/{STEP}/quiz/q2", json={"answer": "lots"}).status_code == 400
    assert client.post(f"/api/steps/{STEP}/quiz/q9", json={"answer": 0}).status_code == 404
    items = {q["id"]: q for q in client.get(f"/api/steps/{STEP}/quiz").json()["items"]}
    assert items["q1"]["last"]["correct"] is True and items["q1"]["last"]["tries"] == 2
    assert items["q3"]["last"] is None and "answer" not in items["q3"]


def test_count_tokens_tool(lab):
    client, _, gateway = lab
    r = client.post("/api/tools/count_tokens", json={"text": "one two three"}).json()
    assert r == {"model": "claude-opus-5-5", "input_tokens": 11, "wrapper_tokens": 8, "text_tokens": 3}
    client.post("/api/tools/count_tokens", json={"text": "four"})
    assert gateway.calls == 3                              # the wrapper is measured once per model
    assert client.post("/api/tools/count_tokens", json={"text": "x", "model": "bad model"}).status_code == 400


def test_count_tokens_without_credentials_is_a_clear_503(make_client):
    r = make_client().post("/api/tools/count_tokens", json={"text": "hi"})
    assert r.status_code == 503 and "anthropic.env" in r.json()["detail"]


# ------------------------------------------------------------------- pages
def test_lab_page_renders_the_lesson_without_raw_html(tmp_path, make_client):
    content = tmp_path / "content"
    shutil.copytree(REPO / "content", content)
    md = content / "m02-agent-loop/lab02-agent-loop/s01-one-call/step.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n<script>alert(1)</script>\n", encoding="utf-8")
    html = make_client(content_dir=content).get(f"/lab/{STEP}").text
    assert "<p>Every agent is one model call" in html                         # step.md, rendered
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html
    assert 'id="guide"' in html and 'id="guide-step"' in html and 'id="marks"' in html
    assert html.count("<h1>") == 1                                            # step.md's own title is dropped


def test_home_shows_spaced_review_and_scores(lab):
    client, store, _ = lab
    record_run(store, "20261109-100000-aaaaaa", events(LOW))
    commit(client, "e2", {"p1": 1, "p2": 1, "p3": 0})                         # p1 wrong: a thinking block came back
    graded_against(client, store, "e2", events(HIGH, effort="high"), "20261109-100100-bbbbbb")
    client.post(f"/api/steps/{STEP}/quiz/q3", json={"answer": 0})
    client.post(f"/api/steps/{STEP}/guide/g2/check", json={"answers": {"c2": 0}})
    html = client.get("/").text
    assert "Spaced review" in html and "At effort high, will a thinking block come back?" in html
    assert "stop_reason came back as" in html and f'href="/lab/{STEP}#quiz"' in html
    assert f'href="/lab/{STEP}#g2"' in html and f'href="/lab/{STEP}#e2"' in html   # back to the right step
    assert "Predictions right" in html and "67%" in html                      # 2 of 3 right


# ------------------------------------------------------------------- guide
def test_guide_teaches_then_shows_your_run(lab):
    client, store, _ = lab
    before = client.get(f"/api/steps/{STEP}/guide").json()
    assert before["run_id"] is None and len(before["steps"]) == 9
    g1 = before["steps"][0]
    assert "<table>" in g1["teach_html"] and g1["lines"] == list(range(5, 14))
    assert [f["value"] for f in g1["show"]] == [None] * 5 and "answer" not in g1["check"][0]
    record_run(store, "20261109-100000-aaaaaa", events(LOW))
    after = client.get(f"/api/steps/{STEP}/guide").json()
    values = {f["key"]: f["value"] for f in after["steps"][0]["show"]}
    assert after["run_id"] == "20261109-100000-aaaaaa"
    assert values == {"request.model": "claude-opus-5-5", "request.max_tokens": 1024, "request.effort": "low",
                      "request.retry_count": 0, "run.first_call_ms": 2900}
    assert [s["experiment"] for s in after["steps"]][4:8] == ["e2", "e3", "e4", "e5"]
    assert after["steps"][8]["quiz"] is True


def test_guide_checks_grade_against_your_run_and_are_recorded(lab):
    client, store, _ = lab
    url = f"/api/steps/{STEP}/guide"
    concept = client.post(f"{url}/g1/check", json={"answers": {"c1": 1}}).json()["results"]["c1"]
    assert concept["correct"] is True and "hard cap" in concept["explanation"]   # no run needed
    about_run = client.post(f"{url}/g2/check", json={"answers": {"c1": 0}})
    assert about_run.status_code == 409 and "press Run first" in about_run.json()["detail"]

    record_run(store, "20261109-100000-aaaaaa", events(LOW))
    blocks = client.post(f"{url}/g2/check", json={"answers": {"c1": 1}}).json()["results"]["c1"]
    assert blocks["correct"] is False and blocks["actual_display"].startswith("Only a text block")
    cost = client.post(f"{url}/g4/check", json={"answers": {"c1": 0.0014}}).json()["results"]["c1"]
    assert cost["correct"] is True                                            # $0.001388, within 2%
    assert client.post(f"{url}/g4/check", json={"answers": {"c1": "cheap"}}).status_code == 400
    assert client.post(f"{url}/g9/check", json={"answers": {"x": 1}}).status_code == 400
    assert client.post(f"{url}/nope/check", json={"answers": {"c1": 1}}).status_code == 404

    wrong = {m["item_id"] for m in store.mistakes("m02")["still_wrong"]}
    assert wrong == {f"{STEP}:g2:c1"}
    step = client.get(url).json()["steps"]
    assert step[1]["answers"]["c1"]["correct"] is False and step[0]["answers"]["c1"]["correct"] is True
