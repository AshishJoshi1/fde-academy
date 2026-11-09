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
            for delta_type, field in (("text_delta", "text"), ("thinking_delta", "thinking")):
                if delta.get("type") == delta_type:
                    block[field] = block.get(field, "") + delta.get(field, "")
        elif kind == "message_delta" and msg is not None:
            msg.update(d.get("delta") or {})
    if msg is None:
        return None
    msg["content"] = [blocks[i] for i in sorted(blocks)]
    return msg


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

    if requests:
        req = requests[-1]["data"]
        body = req.get("body") if isinstance(req.get("body"), dict) else {}
        f["request.model"] = body.get("model")
        f["request.max_tokens"] = body.get("max_tokens")
        f["request.effort"] = (body.get("output_config") or {}).get("effort") or "not set"
        retry = (req.get("headers") or {}).get("x-stainless-retry-count")
        f["request.retry_count"] = int(retry) if str(retry).isdigit() else None

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

    if prev_events is not None:
        prev_out = run_facts(prev_events)["response.usage.output_tokens"]
        f["prev.response.usage.output_tokens"] = prev_out
        out = f["response.usage.output_tokens"]
        if out is not None and prev_out:
            f["ratio.output_tokens"] = round(out / prev_out, 3)
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
