import json
import os
import re
from typing import Literal

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

LOOSE_CLASSIFY = False  # experiment 1: True lets the category be any string
MODEL_ENRICH = False    # experiment 2: True lets the model fetch the facts with a tool
BAD_TICKET = False      # step g7: True adds a fourth ticket about an opportunity that does not exist
ATTEMPTS = 2            # one try, and one retry

TICKETS = [
    "Procurement asked for 12% off on OPP-1042. What do we have on file, and when does it start?",
    "Is OPP-1047 still at proposal stage? Our start date moved and I need to know where it stands.",
    "Please set the discount on OPP-1044 to 15%. Finance will sign off later.",
]
if BAD_TICKET:
    TICKETS.append("What is the status of OPP-1999?")


# ---- The typed hand-offs: what each step must hand to the next one ----------------------------
class Classification(BaseModel):
    category: str if LOOSE_CLASSIFY else Literal["discount_question", "status_question", "change_request"]
    opportunity_id: str


class Facts(BaseModel):  # the only data the reply may use
    opportunity_id: str
    stage: str
    requested_discount_pct: float
    start_date: str
    currency: str


class Reply(BaseModel):
    text: str


class ChainError(Exception):
    pass


def ask(system, user, schema, tools=None):
    """One model call that must answer in the shape of `schema`; the SDK validates it."""
    response = client.messages.parse(
        model=MODEL, max_tokens=2048, output_config={"effort": "low"},
        system=system, messages=user, output_format=schema, **({"tools": tools} if tools else {}))
    return response


# ---- The three steps --------------------------------------------------------------------------
def classify(ticket):
    response = ask(
        "Classify a customer ticket about a sales opportunity. Category: a question about the requested "
        "discount, a question about the stage or start date, or a request to change a record. "
        "Also give the opportunity ID it names.",
        [{"role": "user", "content": ticket}], Classification)
    c = response.parsed_output
    if c.opportunity_id not in ticket:  # a rule the schema can't express: the ID must come from the ticket
        raise ValueError(f"opportunity_id {c.opportunity_id!r} is not in the ticket")
    return c


def enrich_plain(c):  # plain code: no model, no tokens
    r = httpx.get(f"{MERIDIAN}/opportunities/{c.opportunity_id}", headers=AUTH, timeout=10)
    if r.status_code != 200:
        raise ValueError(f"Meridian answered {r.status_code} for {c.opportunity_id}")
    o = r.json()
    return Facts(opportunity_id=o["opportunity_id"], stage=o["stage"], start_date=o["start_date"],
                 requested_discount_pct=o["requested_discount_pct"], currency=o["currency"])


def enrich_model(c):  # the model decides what to fetch, in a loop like s02
    tools = [{"name": "get_opportunity", "description": "Look up one opportunity in the Meridian CRM by ID.",
              "input_schema": {"type": "object", "properties": {"opportunity_id": {"type": "string"}},
                               "required": ["opportunity_id"]}}]
    messages = [{"role": "user", "content": f"Collect the facts for {c.opportunity_id}."}]
    for _ in range(4):
        response = ask("Use the tool, then give the facts of the opportunity.", messages, Facts, tools)
        if response.stop_reason != "tool_use":
            return response.parsed_output
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for b in response.content:
            if b.type == "tool_use":
                r = httpx.get(f"{MERIDIAN}/opportunities/{b.input['opportunity_id']}", headers=AUTH, timeout=10)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": r.text,
                                "is_error": r.status_code != 200})
        messages.append({"role": "user", "content": results})
    raise ValueError("the model never produced the facts")


GUIDE = {
    "discount_question": "Say what discount is on file.",
    "status_question": "Say the stage and the start date.",
    "change_request": "You cannot change records. Say a person will follow up, and what is on file now.",
}


def respond(ticket, c, facts):  # sees the ticket, the category and the facts: not the raw CRM record
    response = ask(
        "Write a short, polite reply to the customer, two sentences at most. Use ONLY these facts: "
        + facts.model_dump_json() + ". " + GUIDE[c.category],
        [{"role": "user", "content": ticket}], Reply)
    reply = response.parsed_output
    allowed = {facts.requested_discount_pct} | {float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", ticket)}
    for pct in re.findall(r"(\d+(?:\.\d+)?)\s*%", reply.text):
        if float(pct) not in allowed:
            raise ValueError(f"the reply says {pct}%, which is in neither the facts nor the ticket")
    return reply


# ---- The chain: run a step, validate it, retry once, then fail naming the step -----------------
def trace(n, step, attempt, inp, out, error):
    record = {"ticket": n, "step": step, "attempt": attempt, "input": inp, "output": out, "error": error}
    print("@@step " + json.dumps(record, default=lambda o: o.model_dump()), flush=True)  # the lab's step view reads this line


def run_step(n, step, shown_input, fn, *args):
    error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            out = fn(*args)
            trace(n, step, attempt, shown_input, out, None)
            return out
        except (ValidationError, ValueError, httpx.HTTPError) as exc:
            error = str(exc).splitlines()[0][:200]
            trace(n, step, attempt, shown_input, None, error)
    raise ChainError(f"step '{step}' failed after {ATTEMPTS} attempts: {error}")


for n, ticket in enumerate(TICKETS, 1):
    print(f"ticket {n}: {ticket}")
    try:
        c = run_step(n, "classify", ticket, classify, ticket)
        facts = run_step(n, "enrich", c, enrich_model if MODEL_ENRICH else enrich_plain, c)
        reply = run_step(n, "respond", {"category": c.category, "facts": facts}, respond, ticket, c, facts)
        print("  reply:", reply.text)
    except ChainError as exc:
        print("  FAILED:", exc)
    except KeyError as exc:  # a category the reply step has no guidance for
        print(f"  CRASHED in respond: no guidance for category {exc}")
