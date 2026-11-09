"""The tutor endpoint against a fake gateway: what the request holds, how threads replay, what's stored."""
from __future__ import annotations

import json

import httpx2
import pytest

from academy_server.relay import Upstream

STEP = "m02.lab02.s01"
URL = f"/api/steps/{STEP}/tutor"


class FakeGateway:
    """Stands in for the gateway: records each /v1/messages body and answers with a thinking
    block and a text block, or with an error when told to."""

    def __init__(self):
        self.bodies: list[dict] = []
        self.fail: int | None = None
        self.stop_reason = "end_turn"

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.fail:
            inner = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "bad field"}})
            return httpx2.Response(self.fail, json={"error": {"message": inner, "code": str(self.fail)}})
        n = len(self.bodies)
        return httpx2.Response(200, headers={"x-litellm-call-id": f"call-{n}"}, json={
            "id": f"msg_{n}", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "thinking", "thinking": "", "signature": f"sig{n}"},
                        {"type": "text", "text": f"What does line 16 print? (answer {n})"}],
            "stop_reason": self.stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 300, "output_tokens": 40, "cache_creation_input_tokens": 5000 if n == 1 else 200,
                      "cache_read_input_tokens": 0 if n == 1 else 5000}})


@pytest.fixture
def gw():
    return FakeGateway()


@pytest.fixture
def client(make_client, gw):
    return make_client(upstream=Upstream("https://fake.gateway", "sk-real-key"), tutor_transport=httpx2.MockTransport(gw))


def test_first_question_builds_the_layered_request(client, gw, home):
    r = client.post(f"{URL}/g2", json={"text": "Why is content a list?"})
    assert r.status_code == 200, r.text
    turn = r.json()["turn"]
    assert turn["role"] == "assistant" and "line 16" in turn["text"] and "<p>" in turn["html"]
    assert turn["usage"]["cache_creation_input_tokens"] == 5000
    assert r.json()["call_id"] == "call-1"

    body = gw.bodies[0]
    assert body["model"] == "claude-sonnet-5-5" and body["output_config"] == {"effort": "low"}
    rules, lesson = body["system"]
    assert "cache_control" not in rules and "tutor" in rules["text"]
    assert lesson["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert lesson["text"].startswith(f'<lesson id="{STEP}"') and "<step_yaml>" in lesson["text"]
    assert "   5  client = anthropic.Anthropic()" in lesson["text"]          # numbered starter
    [msg] = body["messages"]
    context, question = msg["content"]
    assert context["text"].startswith('<lab_context guide_step="g2">') and "cache_control" not in context
    assert "He hasn't run this step yet." in context["text"]
    assert question == {"type": "text", "text": "Why is content a list?", "cache_control": {"type": "ephemeral"}}
    # The rules were copied into the playground, where they're the learner's to edit.
    assert (home / "playground" / "tutor" / "rules.md").is_file()


def test_second_question_replays_the_thread_unchanged(client, gw):
    client.post(f"{URL}/g2", json={"text": "first"})
    r = client.post(f"{URL}/g2", json={"text": "second"})
    assert r.status_code == 200, r.text
    first, second = gw.bodies
    assert first["system"] == second["system"]                       # the cached prefix is byte-identical
    user1, assistant1, user2 = second["messages"]
    assert user1["content"][-1] == {"type": "text", "text": "first"}  # breakpoint moved on; content unchanged
    assert user1["content"][0] == {k: v for k, v in first["messages"][0]["content"][0].items()}
    assert assistant1 == {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "", "signature": "sig1"},
        {"type": "text", "text": "What does line 16 print? (answer 1)"}]}
    # Nothing in the lab changed, so the context isn't sent again.
    assert user2["content"] == [{"type": "text", "text": "(Lab context unchanged since my last question.)\n\nsecond",
                                 "cache_control": {"type": "ephemeral"}}]

    turns = client.get(f"{URL}/g2").json()["turns"]
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
    assert turns[0]["text"] == "first" and turns[3]["usage"]["cache_read_input_tokens"] == 5000


def test_threads_are_per_guide_step_and_context_resent_on_change(client, gw, home):
    client.post(f"{URL}/g2", json={"text": "on g2"})
    client.post(f"{URL}/g3", json={"text": "on g3"})
    assert len(gw.bodies[1]["messages"]) == 1                        # g3 starts its own thread
    main = home / "playground" / STEP / "main.py"
    main.write_text(main.read_text(encoding="utf-8") + "print('edited')\n", encoding="utf-8")
    client.post(f"{URL}/g2", json={"text": "again"})
    newest = gw.bodies[2]["messages"][-1]["content"]
    assert newest[0]["text"].startswith("<lab_context") and "print('edited')" in newest[0]["text"]


def test_open_checks_are_listed_so_the_tutor_keeps_answers_back(client, gw):
    client.post(f"/api/steps/{STEP}/guide/g1/check", json={"answers": {"c1": 1}})
    client.post(f"{URL}/g1", json={"text": "hint please"})
    context = gw.bodies[0]["messages"][0]["content"][0]["text"]
    assert "check c1: answered right" in context
    assert "check c2: not answered yet: don't reveal its answer" in context


def test_spend_is_recorded_as_tutor(client, store):
    client.post(f"{URL}/g2", json={"text": "q"})
    rows = store._query("SELECT source, model, cache_write_tokens, cost_usd FROM spend")
    assert len(rows) == 1 and rows[0]["source"] == "tutor" and rows[0]["model"] == "claude-sonnet-5-5"
    assert rows[0]["cache_write_tokens"] == 5000 and rows[0]["cost_usd"] > 0


def test_show_request_returns_the_exact_body(client, gw):
    turn = client.post(f"{URL}/g2", json={"text": "q"}).json()["turn"]
    r = client.get(f"/api/tutor/turns/{turn['id']}")
    assert r.status_code == 200 and r.json()["request"] == gw.bodies[0]
    assert client.get(f"/api/tutor/turns/{turn['id'] - 1}").status_code == 404   # a question has no request


def test_learner_edits_to_the_rules_are_used(client, gw, home):
    client.post(f"{URL}/g2", json={"text": "q"})
    (home / "playground" / "tutor" / "rules.md").write_text("Answer only in haiku.\n", encoding="utf-8")
    client.post(f"{URL}/g2", json={"text": "q2"})
    assert gw.bodies[1]["system"][0]["text"] == "Answer only in haiku."


def test_gateway_error_is_a_502_and_stores_nothing(client, gw):
    gw.fail = 400
    r = client.post(f"{URL}/g2", json={"text": "q"})
    assert r.status_code == 502 and "bad field" in r.json()["detail"]
    assert client.get(f"{URL}/g2").json()["turns"] == []


def test_refusal_is_reported_and_not_stored(client, gw):
    gw.stop_reason = "refusal"
    r = client.post(f"{URL}/g2", json={"text": "q"})
    assert r.status_code == 422
    assert client.get(f"{URL}/g2").json()["turns"] == []


def test_unknown_guide_step_and_no_gateway(client, make_client):
    assert client.post(f"{URL}/g99", json={"text": "q"}).status_code == 404
    assert make_client().post(f"{URL}/g2", json={"text": "q"}).status_code == 503
