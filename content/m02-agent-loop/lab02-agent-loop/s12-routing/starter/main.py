import json
import os
from typing import Literal

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

EARLY_EXIT = True        # experiment 2: False sends every ticket down the full path
VAGUE_TICKET = False     # step g8: True adds a sixth ticket that says almost nothing
CONFIDENCE_GATE = True   # step g8: False trusts the classifier even when it says it is unsure

TICKETS = [
    "Procurement asked for 12% off on OPP-1042. What do we have on file, and when does it start?",
    "Is OPP-1047 still at proposal stage? Our start date moved and I need to know where it stands.",
    "Please set the discount on OPP-1044 to 15%. Finance will sign off later.",
    "Is OPP-1047 still at proposal stage? And please set its discount to 9% while you are at it.",
    "CONGRATULATIONS! You were selected for a free cruise. Click http://prize.example now to claim it.",
]
if VAGUE_TICKET:
    TICKETS.append("Hi, any news on the thing we talked about last week?")


# ---- The route map and its precedence: data, not if-statements ----------------------------------
ROUTES = {
    "spam": {"canned": "Thank you for your message. It was not a customer request, so no action was taken."},
    "human": {"canned": "A person will review your message and reply."},
    "change_request": {"guide": "You cannot change records. Say a person will follow up, and what is on file now."},
    "discount_question": {"guide": "Say what discount is on file."},
    "status_question": {"guide": "Say the stage and the start date."},
}
PRECEDENCE = ["spam", "change_request", "discount_question", "status_question"]  # first match wins (E1)


# ---- The typed hand-offs ---------------------------------------------------------------------
class Classification(BaseModel):  # classified ONCE: nothing downstream asks the model again
    categories: list[Literal["discount_question", "status_question", "change_request", "spam"]]
    confidence: Literal["high", "low"]
    opportunity_id: str  # empty when the ticket names none


class Facts(BaseModel):  # the only data a reply may use
    opportunity_id: str
    stage: str
    requested_discount_pct: float
    start_date: str
    currency: str


class Reply(BaseModel):
    text: str


calls = 0


def ask(system, user, schema):
    """One model call that must answer in the shape of `schema`; the SDK validates it."""
    global calls
    calls += 1
    return client.messages.parse(model=MODEL, max_tokens=2048, output_config={"effort": "low"},
                                 system=system, messages=[{"role": "user", "content": user}],
                                 output_format=schema).parsed_output


# ---- The steps ---------------------------------------------------------------------------------
def classify(ticket):
    c = ask("Classify a customer ticket about a sales opportunity. List EVERY category that applies: a question "
            "about the requested discount, a question about the stage or start date, a request to change a "
            "record, or spam (not a customer request). Say confidence low if you are unsure. Give the opportunity "
            "ID the ticket names, or an empty string if it names none.", ticket, Classification)
    if c.opportunity_id and c.opportunity_id not in ticket:  # a rule the schema can't express
        raise ValueError(f"opportunity_id {c.opportunity_id!r} is not in the ticket")
    return c


def pick_route(c):
    """Return (route, rule): the one route this ticket takes, and why."""
    if CONFIDENCE_GATE and c.confidence == "low":
        return "human", "confidence is low"
    for name in PRECEDENCE:
        if name in c.categories:
            return name, f"{name} is first in PRECEDENCE among {c.categories}"
    return "human", "no category matched"


def enrich(opportunity_id):  # plain code, as in s11
    r = httpx.get(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10)
    if r.status_code != 200:
        raise ValueError(f"Meridian answered {r.status_code} for {opportunity_id}")
    o = r.json()
    return Facts(opportunity_id=o["opportunity_id"], stage=o["stage"], start_date=o["start_date"],
                 requested_discount_pct=o["requested_discount_pct"], currency=o["currency"])


def respond(ticket, route, facts):
    guide = ROUTES[route].get("guide", "Reply politely and briefly.")
    given = facts.model_dump_json() if facts else "none"
    return ask("Write a short, polite reply to the customer, two sentences at most. Use ONLY these facts: "
               + given + ". " + guide, ticket, Reply)


# ---- The router: classify once, pick a route, run only what that route needs -------------------
def handle(n, ticket):
    start, ran, skipped, exited = calls, ["classify"], [], False
    c = None
    for attempt in range(2):  # one try, and one retry
        try:
            c = classify(ticket)
            break
        except (ValidationError, ValueError) as exc:
            if attempt == 1:
                raise ValueError(f"classify failed twice: {str(exc).splitlines()[0][:150]}")
    route, rule = pick_route(c)
    if "canned" in ROUTES[route] and EARLY_EXIT:  # the cheap exit: nothing else runs
        reply, skipped, exited = ROUTES[route]["canned"], ["enrich", "respond"], True
    else:
        facts = None
        if c.opportunity_id:
            facts = enrich(c.opportunity_id)
            ran.append("enrich")
        else:
            skipped.append("enrich")
        reply = respond(ticket, route, facts).text
        ran.append("respond")
    record = {"ticket": n, "text": ticket, "categories": c.categories, "confidence": c.confidence,
              "route": route, "rule": rule, "exit": exited, "ran": ran,
              "skipped": skipped, "model_calls": calls - start, "reply": reply}
    print("@@route " + json.dumps(record), flush=True)  # the lab's decision view reads this line
    return reply


for n, ticket in enumerate(TICKETS, 1):
    print(f"ticket {n}: {ticket}")
    try:
        print("  reply:", handle(n, ticket))
    except (ValidationError, ValueError, httpx.HTTPError) as exc:
        print("@@route " + json.dumps({"ticket": n, "text": ticket, "route": "failed", "error": str(exc)[:200],
                                       "ran": [], "skipped": [], "model_calls": 0}), flush=True)
        print("  FAILED:", exc)
