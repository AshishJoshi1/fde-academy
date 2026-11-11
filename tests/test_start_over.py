"""Start over: a marker per lesson step. The lab shows only what came after it; nothing is deleted,
so spaced review, quiz history, spend and run history keep everything."""
from __future__ import annotations

import httpx2
import pytest
from test_experiments import LOW, events, record_run
from test_tutor import FakeGateway

from academy_server.relay import Upstream

STEP = "m02.lab02.s01"
API = f"/api/steps/{STEP}"
C2 = f"{STEP}:g1:c2"


def miss(store, item=C2):
    store.record_quiz_attempt(item_id=item, module_id="m02", type="mcq", answer=0, correct=False, step_id=STEP)


# ------------------------------------------------------------------- store
def test_marker_hides_earlier_answers_from_the_lab_but_not_from_review(store):
    miss(store)
    assert store.started_over_at(STEP) is None
    at = store.start_over([(STEP, "m02")])
    assert store.started_over_at(STEP) == at
    assert store.quiz_latest(STEP, at) == {}                         # the lab: a fresh step
    assert C2 in store.quiz_latest(STEP)                             # without since: everything
    assert [m["item_id"] for m in store.mistakes()["still_wrong"]] == [C2]

    store.record_quiz_attempt(item_id=C2, module_id="m02", type="mcq", answer=1, correct=True, step_id=STEP)
    fresh = store.quiz_latest(STEP, at)[C2]                          # written right after: shown
    assert fresh["correct"] is True and fresh["tries"] == 1
    assert [m["item_id"] for m in store.mistakes()["fixed_after_retry"]] == [C2]


def test_marker_applies_to_runs_experiments_and_tutor_threads(store):
    record_run(store, "20261111-090000-aaaaaa", events(LOW))
    store.commit_predictions(STEP, "m02", "e2", [{"item_id": "p1", "type": "mcq", "answer": 0}])   # never run
    store.add_tutor_exchange(STEP, "g2", question="why?", sent=[], answer="What does line 16 print?", blocks=[],
                             request={}, usage=None, model="claude-sonnet-5-5", ms=1, cost_usd=0.0)
    store.record_spend("run", 0.01)
    at = store.start_over([(STEP, "m02")])

    assert store.runs_for_step(STEP, since=at) == [] and len(store.runs_for_step(STEP)) == 1
    assert store.attempts(STEP, "e2", at) == [] and len(store.attempts(STEP, "e2")) == 1
    assert store.tutor_thread(STEP, "g2", at) == [] and len(store.tutor_thread(STEP, "g2")) == 2
    assert store.spend_summary()["total_usd"] == 0.01

    # The old attempt was committed but never run. It doesn't block new predictions after a start over.
    with pytest.raises(ValueError):
        store.commit_predictions(STEP, "m02", "e2", [{"item_id": "p1", "type": "mcq", "answer": 1}])
    new = store.commit_predictions(STEP, "m02", "e2", [{"item_id": "p1", "type": "mcq", "answer": 1}], since=at)
    assert new["attempt"] == 2 and [a["attempt"] for a in store.attempts(STEP, "e2", at)] == [2]


def test_start_over_resets_the_step_status_and_survives_export(store, home):
    store.open_step(STEP, "m02")
    store.complete_step(STEP, "m02", {"main.py": "x = 1\n"})
    at = store.start_over([(STEP, "m02")], code_reset=True)
    assert store.step_status()[STEP] == "in_progress"

    data = store.export_all()
    assert data["tables"]["step_restarts"] == [{"id": 1, "step_id": STEP, "at": at, "code_reset": 1}]
    from academy_server.store import Store
    other = Store(home / "other.db")
    other.import_all(data)
    assert other.started_over_at(STEP) == at
    other.close()


# --------------------------------------------------------------------- API
@pytest.fixture
def client(make_client):
    return make_client(upstream=Upstream("https://fake.gateway", "sk-real-key"),
                       tutor_transport=httpx2.MockTransport(FakeGateway()))


def test_start_over_gives_a_fresh_lesson_and_keeps_history(client):
    store = client.app.state.store
    assert client.post(f"{API}/guide/g1/check", json={"answers": {"c2": 0}}).json()["results"]["c2"]["correct"] is False
    client.post(f"{API}/quiz/q1", json={"answer": 0})
    record_run(store, "20261111-090000-aaaaaa", events(LOW))
    assert client.post(f"{API}/tutor/g2", json={"text": "Why a list?"}).status_code == 200
    assert client.get(f"{API}/guide").json()["run_id"] == "20261111-090000-aaaaaa"

    r = client.post(f"{API}/start-over", json={})
    assert r.status_code == 200, r.text
    assert r.json()["steps"] == [STEP] and r.json()["code_reset"] == []

    guide = client.get(f"{API}/guide").json()
    assert guide["run_id"] is None and not any(g["answers"] for g in guide["steps"])
    assert all(q["last"] is None for q in client.get(f"{API}/quiz").json()["items"])
    assert all(c["status"] == "predict" for c in client.get(f"{API}/experiments").json()["experiments"])
    assert client.get(f"{API}/tutor/g2").json()["turns"] == []
    runs = client.get(f"{API}/runs").json()
    assert [x["run_id"] for x in runs["runs"]] == ["20261111-090000-aaaaaa"]       # history keeps every run
    assert runs["started_over_at"] == r.json()["started_over_at"]                  # the page doesn't reopen it

    still = {m["item_id"] for m in client.get("/api/mistakes").json()["still_wrong"]}
    assert C2 in still                                                             # spaced review keeps the miss
    assert client.post(f"{API}/guide/g1/check", json={"answers": {"c2": 1}}).json()["results"]["c2"]["correct"]
    fixed = {m["item_id"] for m in client.get("/api/mistakes").json()["fixed_after_retry"]}
    assert C2 in fixed


def test_start_over_can_reset_the_code_too(client, home):
    main = home / "playground" / STEP / "main.py"
    client.get(f"{API}/files")                                       # first use copies the starter
    starter = main.read_text(encoding="utf-8")
    main.write_text("print('my edit')\n", encoding="utf-8")
    assert client.post(f"{API}/start-over", json={"code": False}).json()["code_reset"] == []
    assert main.read_text(encoding="utf-8") == "print('my edit')\n"
    assert client.post(f"{API}/start-over", json={"code": True}).json()["code_reset"] == [STEP]
    assert main.read_text(encoding="utf-8") == starter


def test_start_all_over_marks_every_step_and_never_creates_a_playground(client, home):
    r = client.post("/api/start-over", json={"code": True})
    assert r.status_code == 200
    assert r.json()["steps"] == [STEP] and r.json()["code_reset"] == []
    assert not (home / "playground" / STEP).exists()
    assert client.app.state.store.started_over_at(STEP) == r.json()["started_over_at"]


def test_start_over_pages(client):
    lab = client.get(f"/lab/{STEP}").text
    assert f'data-endpoint="/api/steps/{STEP}/start-over"' in lab and "Start this lesson over" in lab
    assert "{{start_over" not in lab
    home = client.get("/").text
    assert 'data-endpoint="/api/start-over"' in home and "Start over all lessons" in home
    assert client.post("/api/steps/m09.x.s1/start-over", json={}).status_code == 404
