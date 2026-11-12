"""Experiments: measure a run, grade predictions against it, diff it against the previous run.

A run's facts (content.schema.FACTS) are the values a prediction can be graded against.
They're read from the run's own events, the same record the lab page shows, so every
grade can be checked by reopening the run.
"""
from __future__ import annotations

import bisect
import difflib
import json
import math
from typing import Any

from .content.schema import FACTS, MCQ, Numeric, Option, PredictMCQ, PredictNumeric, PredictText

COST_MATCH_REL = 0.001   # relay and gateway costs "agree" within 0.1% (float noise in the header)


# ------------------------------------------------------------------- facts
def _message(body: Any) -> dict[str, Any] | None:
    """The Message a call returned: the JSON body, or rebuilt from a stream's events."""
    if not isinstance(body, dict):
        return None
    if body.get("type") == "message":
        return body
    if not isinstance(body.get("events"), list):
        return None
    msg: dict[str, Any] | None = None
    blocks: dict[int, dict[str, Any]] = {}
    for ev in body["events"]:
        d = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        kind = d.get("type")
        if kind == "message_start":
            msg = dict(d.get("message") or {})
        elif kind == "content_block_start":
            blocks[d.get("index", len(blocks))] = dict(d.get("content_block") or {})
        elif kind == "content_block_delta":
            block, delta = blocks.setdefault(d.get("index", 0), {}), d.get("delta") or {}
            for delta_type, field in (("text_delta", "text"), ("thinking_delta", "thinking"),
                                      ("input_json_delta", "partial_json")):
                if delta.get("type") == delta_type:
                    block[field] = block.get(field, "") + delta.get(field, "")
        elif kind == "message_delta" and msg is not None:
            msg.update(d.get("delta") or {})
    if msg is None:
        return None
    for block in blocks.values():          # a streamed tool_use sends its input as JSON fragments
        if "partial_json" in block:
            try:
                block["input"] = json.loads(block.pop("partial_json") or "{}")
            except ValueError:
                pass
    msg["content"] = [blocks[i] for i in sorted(blocks)]
    return msg


def message_shape(message: Any) -> str:
    """A request message in a few words: its role and its block types, e.g. 'user: tool_result'."""
    if not isinstance(message, dict):
        return "?"
    content = message.get("content")
    kinds = "text" if isinstance(content, str) else ", ".join(
        str(b.get("type", "?")) if isinstance(b, dict) else "?" for b in (content or [])) or "(empty)"
    return f"{message.get('role', '?')}: {kinds}"


def error_message(body: Any) -> str | None:
    """The message of an error body. The gateway puts Anthropic's error JSON, as a string,
    at the start of its own message; that inner message is the useful one."""
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict) or not isinstance(err.get("message"), str):
        return None if body is None else str(body)[:500]
    msg = err["message"]
    if msg.lstrip().startswith("{"):
        try:
            inner, _ = json.JSONDecoder().raw_decode(msg.lstrip())
            return (inner.get("error") or {}).get("message") or msg
        except (ValueError, AttributeError):
            pass
    return msg


def _blocks(message: Any) -> list[dict[str, Any]]:
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def results_in_one_message(messages: list[Any]) -> bool | None:
    """Whether every assistant turn's tool_use blocks are all answered by tool_results in the one user
    message right after it. None when no assistant turn asked for a tool.

    The API rejects a tool_use with no tool_result in the next message (s02), but it accepts results
    split over several user messages in a row, because it joins them: only this check catches that."""
    verdicts = []
    for i, m in enumerate(messages):
        ids = {b.get("id") for b in _blocks(m) if b.get("type") == "tool_use"}
        if not ids or not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        after = []
        for nxt in messages[i + 1:]:
            if isinstance(nxt, dict) and nxt.get("role") == "assistant":
                break
            after.append(nxt)
        with_results = [n for n in after if any(b.get("type") == "tool_result" for b in _blocks(n))]
        answered = {b.get("tool_use_id") for b in _blocks(after[0]) if b.get("type") == "tool_result"} if after else set()
        verdicts.append(len(with_results) == 1 and with_results[0] is after[0] and ids <= answered)
    return all(verdicts) if verdicts else None


_JSON_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict, "array": list}


def input_problems(schema: Any, value: Any) -> list[str]:
    """What is wrong with a tool input judged against its input_schema: types, required,
    additionalProperties and enum (the parts a strict schema guarantees)."""
    if not isinstance(schema, dict):
        return []
    kind = schema.get("type")
    py = _JSON_TYPES.get(kind) if isinstance(kind, str) else None
    if py is not None and (not isinstance(value, py) or (isinstance(value, bool) and kind != "boolean")):
        return [f"{value!r} is not {kind}"]
    found: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{value!r} not in enum")
    if kind == "object" and isinstance(value, dict):
        props = schema.get("properties") or {}
        found += [f"missing {k}" for k in schema.get("required") or [] if k not in value]
        if schema.get("additionalProperties") is False:
            found += [f"unexpected {k}" for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                found += input_problems(sub, value[k])
    return found


def _events(events: list[dict[str, Any]], *types: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] in types]


def answer_text(events: list[dict[str, Any]]) -> str:
    """The text blocks of the run's last response, joined."""
    responses = _events(events, "llm.response")
    msg = _message(responses[-1]["data"].get("body")) if responses else None
    return "".join(b.get("text", "") for b in (msg or {}).get("content", []) if b.get("type") == "text")


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_facts(events: list[dict[str, Any]], prev_events: list[dict[str, Any]] | None = None,
              text_tokens: int | None = None) -> dict[str, Any]:
    """Every FACTS key, measured from a run's events. None where the run didn't produce it.

    text_tokens is the count_tokens measure of answer_text(events); the caller gets it
    from the gateway, because counting needs a model's tokenizer.
    """
    f: dict[str, Any] = dict.fromkeys(FACTS)
    started = _events(events, "run.started")
    ended = _events(events, "run.exit")
    requests = _events(events, "llm.request")
    results = _events(events, "llm.response", "llm.error")
    f["run.model"] = started[0]["data"].get("model") if started else None
    f["run.outcome"] = ended[-1]["data"].get("outcome") if ended else None
    f["run.calls"] = len(requests)
    f["run.first_call_ms"] = requests[0]["t_ms"] if requests else None
    responses = _events(events, "llm.response")
    if responses:
        f["run.cost_usd"] = round(sum(r["data"].get("cost_usd") or 0 for r in responses), 8)
        ins = [(r["data"].get("usage") or {}).get("input_tokens") for r in responses]
        if any(n is not None for n in ins):
            f["run.input_tokens"] = sum(n or 0 for n in ins)

    if requests:
        req = requests[-1]["data"]
        body = req.get("body") if isinstance(req.get("body"), dict) else {}
        f["request.model"] = body.get("model")
        f["request.max_tokens"] = body.get("max_tokens")
        f["request.effort"] = (body.get("output_config") or {}).get("effort") or "not set"
        retry = (req.get("headers") or {}).get("x-stainless-retry-count")
        helper = (req.get("headers") or {}).get("x-stainless-helper")   # the SDK's tool runner tags its calls
        f["request.helper"] = str(helper) if helper else "not set"
        beta = (req.get("headers") or {}).get("anthropic-beta")
        f["request.beta"] = str(beta) if beta else "not set"
        f["request.retry_count"] = int(retry) if str(retry).isdigit() else None
        tools = body.get("tools") if isinstance(body.get("tools"), list) else []
        f["request.strict"] = ("on, every tool" if tools and all(isinstance(t, dict) and t.get("strict") is True for t in tools)
                               else "off")
        f["request.tool_names"] = ", ".join(str(t.get("name", "?")) for t in tools if isinstance(t, dict)) or "(none)"
        msgs = body.get("messages")
        if isinstance(msgs, list):
            f["request.messages"] = len(msgs)
            f["request.last_message"] = message_shape(msgs[-1]) if msgs else "(none)"
            # The last request carries the whole history, so its tool_results are every result sent.
            results_sent = [b for m in msgs for b in _blocks(m) if b.get("type") == "tool_result"]
            f["loop.tool_results"] = len(results_sent)
            f["loop.error_results"] = sum(1 for b in results_sent if b.get("is_error"))
            f["loop.blocked_results"] = sum(1 for b in results_sent if b.get("is_error") and str(b.get("content", "")).startswith("BLOCKED"))
            f["loop.denied_results"] = sum(1 for b in results_sent if b.get("is_error") and str(b.get("content", "")).startswith("DENIED"))
            f["loop.results_in_one_message"] = results_in_one_message(msgs)
        # History only grows: every call resends the previous call's messages, unchanged, then adds to them.
        lists = [r["data"]["body"]["messages"] for r in requests
                 if isinstance(r["data"].get("body"), dict) and isinstance(r["data"]["body"].get("messages"), list)]
        if lists:
            f["request.history_grows"] = all(cur[:len(prev)] == prev for prev, cur in zip(lists, lists[1:]))

    last = results[-1] if results else None
    if last and last["type"] == "llm.response":
        d = last["data"]
        f["response.status"] = d.get("status")
        f["response.ms"] = d.get("ms")
        usage = d.get("usage") or {}
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            f[f"response.usage.{key}"] = usage.get(key)
        f["response.cost_usd"] = d.get("cost_usd")
        f["response.gateway_cost_usd"] = _float((d.get("headers") or {}).get("x-litellm-response-cost-original"))
        ours, theirs = f["response.cost_usd"], f["response.gateway_cost_usd"]
        if ours is not None and theirs is not None:
            f["response.cost_matches_gateway"] = math.isclose(ours, theirs, rel_tol=COST_MATCH_REL, abs_tol=1e-12)
        if (d.get("status") or 0) >= 400:
            f["response.error_message"] = error_message(d.get("body"))
        msg = _message(d.get("body"))
        if msg is not None:
            content = msg.get("content") or []
            types = [b.get("type") for b in content]
            thinking = [b.get("thinking") or "" for b in content if b.get("type") == "thinking"]
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            f["response.stop_reason"] = msg.get("stop_reason")
            f["response.blocks"] = ", ".join(types) if types else "(none)"
            f["response.has_thinking"] = bool(thinking)
            f["response.thinking_text"] = ("none" if not thinking
                                           else "readable" if any(t.strip() for t in thinking) else "empty")
            f["response.has_text"] = bool(text.strip())
            f["response.text_chars"] = len(text)
            if text_tokens is not None:
                f["response.text_tokens"] = text_tokens
                if usage.get("output_tokens") is not None:
                    f["response.hidden_output_tokens"] = usage["output_tokens"] - text_tokens

    if responses:
        first = responses[0]["data"]
        f["first.response.usage.input_tokens"] = (first.get("usage") or {}).get("input_tokens")
        msg = _message(first.get("body"))
        if msg is not None:
            content = msg.get("content") or []
            f["first.response.stop_reason"] = msg.get("stop_reason")
            f["first.response.blocks"] = ", ".join(str(b.get("type")) for b in content) or "(none)"
            uses = [b for b in content if b.get("type") == "tool_use"]
            f["first.response.tool_uses"] = len(uses)
            if uses:
                f["first.response.tool_name"] = uses[0].get("name")
                f["first.response.tool_input"] = json.dumps(uses[0].get("input"), ensure_ascii=False)
                f["first.response.tool_inputs"] = ", ".join(json.dumps(b.get("input"), ensure_ascii=False) for b in uses)
        first_in, last_in = f["first.response.usage.input_tokens"], f["response.usage.input_tokens"]
        if first_in and last_in is not None:
            f["loop.input_growth"] = last_in - first_in
            f["loop.input_ratio"] = round(last_in / first_in, 3)

    if requests:      # the tool inputs the model wrote, judged against the schema of the request that got them
        uses = invalid = no_tool = 0
        for req, res in zip(requests, results):
            body = req["data"].get("body") if isinstance(req["data"].get("body"), dict) else {}
            schemas = {t.get("name"): t.get("input_schema") for t in body.get("tools") or [] if isinstance(t, dict)}
            msg = _message(res["data"].get("body")) if res["type"] == "llm.response" else None
            blocks = [b for b in (msg or {}).get("content") or [] if b.get("type") == "tool_use"]
            if msg is not None and not blocks:
                no_tool += 1
            uses += len(blocks)
            invalid += sum(1 for b in blocks if input_problems(schemas.get(b.get("name")), b.get("input")))
        f["fuzz.tool_uses"], f["fuzz.invalid"], f["fuzz.no_tool"] = uses, invalid, no_tool

    asked = _events(events, "approval.requested")
    answered = [a["data"].get("outcome") for a in _events(events, "approval.answered")]
    f["approval.asked"] = len(asked)
    f["approval.approved"] = answered.count("approved")
    f["approval.denied"] = len(answered) - answered.count("approved")   # denied, timed out or run ended

    if started and started[0]["data"].get("fixture"):       # only a step with a mock API measures these
        api = _events(events, "api.request")
        f["api.requests"] = len(api)
        f["api.writes"] = sum(1 for a in api if a["data"].get("method") != "GET")
        if api:
            a = api[-1]["data"]
            f["api.last_request"] = f"{a.get('method')} {a.get('path')}{'?' + a['query'] if a.get('query') else ''} → {a.get('status')}"

    if prev_events is not None:
        prev = run_facts(prev_events)
        prev_out = prev["response.usage.output_tokens"]
        f["prev.response.usage.output_tokens"] = prev_out
        out = f["response.usage.output_tokens"]
        if out is not None and prev_out:
            f["ratio.output_tokens"] = round(out / prev_out, 3)
        prev_in = prev["run.input_tokens"]
        f["prev.run.input_tokens"] = prev_in
        if f["run.input_tokens"] is not None and prev_in:
            f["ratio.input_tokens"] = round(f["run.input_tokens"] / prev_in, 3)
    return f


# ----------------------------------------------------------------- grading
def _label(option: str | Option) -> str:
    return option.label if isinstance(option, Option) else option


def _option_for(item: PredictMCQ, value: Any) -> int | None:
    """Which option a measured value stands for."""
    if item.bins is not None:
        number = _float(value)
        return None if number is None else bisect.bisect_right(item.bins, number)

    def norm(v: Any) -> str:
        return ("yes" if v else "no") if isinstance(v, bool) else str(v).strip().lower()

    for i, option in enumerate(item.options):
        candidates = [option.value, option.label] if isinstance(option, Option) else [option]
        if any(norm(c) == norm(value) for c in candidates):
            return i
    return None


def _within(item: PredictNumeric | Numeric, guess: float, actual: float) -> bool:
    tol_pct = getattr(item, "tol_pct", None)
    tol_factor = getattr(item, "tol_factor", None)
    if tol_pct is not None:
        return abs(guess - actual) <= abs(actual) * tol_pct / 100
    if tol_factor is not None:
        if actual <= 0 or guess <= 0:
            return guess == actual
        return actual / tol_factor <= guess <= actual * tol_factor
    return abs(guess - actual) <= (item.tol or 0) + 1e-9


def tolerance_text(item: PredictNumeric) -> str:
    if item.tol_pct is not None:
        return f"within {item.tol_pct:g}%"
    if item.tol_factor is not None:
        return f"within a factor of {item.tol_factor:g}"
    return f"within {item.tol:g}" if item.tol else "exactly"


def check_answer(item: PredictMCQ | PredictNumeric | PredictText, answer: Any) -> Any:
    """The learner's answer, validated and normalized for its item type. Raises ValueError."""
    if isinstance(item, PredictMCQ):
        if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(item.options):
            raise ValueError(f"{item.id}: pick one of the {len(item.options)} options")
        return answer
    if isinstance(item, PredictNumeric):
        number = _float(answer)
        if isinstance(answer, bool) or number is None or not math.isfinite(number):
            raise ValueError(f"{item.id}: enter a number")
        return number
    text = str(answer or "").strip()
    if not text or len(text) > 2000:
        raise ValueError(f"{item.id}: write an answer (up to 2,000 characters)")
    return text


def grade(item: PredictMCQ | PredictNumeric | PredictText, answer: Any, facts: dict[str, Any]) -> dict[str, Any]:
    """{correct: True | False | None, actual, actual_display, note}. None means not graded:
    a text prediction, or a value the run didn't produce (say, no response came back)."""
    if isinstance(item, PredictText):
        actual = facts.get(item.show_from) if item.show_from else None
        return {"correct": None, "actual": actual, "actual_display": "" if actual is None else str(actual),
                "note": "your own words: compare them with the explanation"}
    if isinstance(item, PredictMCQ):
        if item.answer_from is None:
            return {"correct": answer == item.answer, "actual": item.answer,
                    "actual_display": _label(item.options[item.answer]), "note": ""}
        value = facts.get(item.answer_from)
        if value is None:
            return {"correct": None, "actual": None, "actual_display": "not measured",
                    "note": f"this run produced no {item.answer_from}"}
        index = _option_for(item, value)
        shown = value if not isinstance(value, bool) else ("yes" if value else "no")
        if index is None:
            return {"correct": False, "actual": value, "actual_display": str(shown),
                    "note": f"{item.answer_from} was {shown!s}, which none of the options matched"}
        display = _label(item.options[index])
        if item.bins is not None or str(shown).lower() != display.lower():
            display = f"{display} ({item.answer_from} = {shown})"
        return {"correct": answer == index, "actual": value, "actual_option": index,
                "actual_display": display, "note": ""}
    expected = item.answer if item.answer_from is None else _float(facts.get(item.answer_from))
    if expected is None:
        return {"correct": None, "actual": None, "actual_display": "not measured",
                "note": f"this run produced no {item.answer_from}"}
    unit = f" {item.unit}" if item.unit else ""
    return {"correct": _within(item, float(answer), expected), "actual": expected,
            "actual_display": f"{expected:g}{unit}", "note": f"right if {tolerance_text(item)}"}


def grade_quiz(item: Any, answer: Any) -> tuple[bool, Any]:
    """(correct, the correct answer) for the quiz types the lab page asks."""
    if isinstance(item, MCQ):
        right = item.answer if isinstance(item.answer, list) else [item.answer]
        chosen = answer if isinstance(answer, list) else [answer]
        if not all(isinstance(a, int) and not isinstance(a, bool) and 0 <= a < len(item.options) for a in chosen):
            raise ValueError(f"pick one of the {len(item.options)} options")
        return sorted(chosen) == sorted(right), item.answer
    if isinstance(item, Numeric):
        number = _float(answer)
        if number is None or isinstance(answer, bool) or not math.isfinite(number):
            raise ValueError("enter a number")
        return _within(item, number, item.answer), item.answer
    raise ValueError(f"the lab page doesn't ask {item.type} items yet")


# -------------------------------------------------------------------- diff
def code_diff(before: dict[str, str], after: dict[str, str]) -> str:
    """Unified diff of every file, previous run first. Empty when nothing changed."""
    out: list[str] = []
    for name in sorted(set(before) | set(after)):
        out += difflib.unified_diff(before.get(name, "").splitlines(keepends=True),
                                    after.get(name, "").splitlines(keepends=True),
                                    fromfile=f"previous run/{name}", tofile=f"this run/{name}", n=2)
    return "".join(line if line.endswith("\n") else line + "\n" for line in out)
