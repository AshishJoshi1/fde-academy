import json
import os
import re
from operator import add
from typing import Annotated, Literal, TypedDict

import anthropic
import httpx
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

TRACE_REDUCER = True   # experiment 1: False takes the reducer off `trace`, so each node overwrites it
RETRY_GUARD = True     # experiment 2: False lets the retry edge loop with no limit of its own
BAD_TICKET = False     # step g7: True adds a fourth ticket about an opportunity that does not exist
ATTEMPTS = 2           # one try, and one retry
RECURSION_LIMIT = 12   # the graph's safety net: the most node visits one ticket may take

TICKETS = [
    "Procurement asked for 12% off on OPP-1042. What do we have on file, and when does it start?",
    "Is OPP-1047 still at proposal stage? Our start date moved and I need to know where it stands.",
    "Please set the discount on OPP-1044 to 15%. Finance will sign off later.",
]
if BAD_TICKET:
    TICKETS.append("What is the status of OPP-1999?")


# ---- The typed hand-offs, the same three as lesson 10 --------------------------------------------
class Classification(BaseModel):
    category: Literal["discount_question", "status_question", "change_request"]
    opportunity_id: str


class Facts(BaseModel):  # the only data the reply may use
    opportunity_id: str
    stage: str
    requested_discount_pct: float
    start_date: str
    currency: str


class Reply(BaseModel):
    text: str


# ---- The state: the one object every node reads, and returns a piece of ---------------------------
class TicketState(TypedDict):
    ticket: str
    classification: Classification | None
    facts: Facts | None
    reply: Reply | None
    error: str | None        # the last failure, or None when the last node passed
    tries: int               # failures in a row for the current node
    failed_step: str | None  # set by the `fail` node
    trace: Annotated[list, add] if TRACE_REDUCER else list   # every node visited, in order


def ask(system, user, schema):
    """One model call that must answer in the shape of `schema`; the SDK validates it."""
    return client.messages.parse(
        model=MODEL, max_tokens=2048, output_config={"effort": "low"},
        system=system, messages=user, output_format=schema)


# ---- The three steps, as plain functions: the same work as lesson 10 ------------------------------
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


def enrich(c):  # plain code: no model, no tokens
    r = httpx.get(f"{MERIDIAN}/opportunities/{c.opportunity_id}", headers=AUTH, timeout=10)
    if r.status_code != 200:
        raise ValueError(f"Meridian answered {r.status_code} for {c.opportunity_id}")
    o = r.json()
    return Facts(opportunity_id=o["opportunity_id"], stage=o["stage"], start_date=o["start_date"],
                 requested_discount_pct=o["requested_discount_pct"], currency=o["currency"])


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


# ---- The nodes: each takes the state and returns only the keys it changes -------------------------
def attempt(name, state, work):
    try:
        return {**work(), "error": None, "tries": 0, "trace": [name]}
    except (ValidationError, ValueError, httpx.HTTPError) as exc:
        return {"error": str(exc).splitlines()[0][:200], "tries": state["tries"] + 1, "trace": [name]}


def classify_node(state):
    return attempt("classify", state, lambda: {"classification": classify(state["ticket"])})


def enrich_node(state):
    return attempt("enrich", state, lambda: {"facts": enrich(state["classification"])})


def respond_node(state):
    return attempt("respond", state, lambda: {"reply": respond(state["ticket"], state["classification"], state["facts"])})


def fail_node(state):
    return {"failed_step": state["trace"][-1], "trace": ["fail"]}


# ---- The edges: go on, retry the node that just failed, or give up ---------------------------------
def retry_or(next_node):
    def route(state):
        if not state["error"]:
            return next_node
        if RETRY_GUARD and state["tries"] >= ATTEMPTS:
            return "fail"
        return state["trace"][-1]  # back to the node that just failed
    return route


graph = StateGraph(TicketState)
graph.add_node("classify", classify_node)
graph.add_node("enrich", enrich_node)
graph.add_node("respond", respond_node)
graph.add_node("fail", fail_node)
graph.add_edge(START, "classify")
for step, nxt in [("classify", "enrich"), ("enrich", "respond"), ("respond", END)]:
    graph.add_conditional_edges(step, retry_or(nxt), {nxt: nxt, step: step, "fail": "fail"})
graph.add_edge("fail", END)
app = graph.compile()


# ---- Run the graph on each ticket, and print the state after every node ----------------------------
def show(n, visit, state):
    record = {"ticket": n, "visit": visit, "node": state["trace"][-1],
              "state": {k: v for k, v in state.items() if k != "ticket"}}
    print("@@graph " + json.dumps(record, default=lambda o: o.model_dump()), flush=True)  # the lab's graph view reads this line


for n, ticket in enumerate(TICKETS, 1):
    print(f"ticket {n}: {ticket}")
    state = {"ticket": ticket, "classification": None, "facts": None, "reply": None,
             "error": None, "tries": 0, "failed_step": None, "trace": []}
    visit = 0
    try:
        for state in app.stream(state, {"recursion_limit": RECURSION_LIMIT}, stream_mode="values"):
            if state["trace"]:  # the first chunk is the input, before any node ran
                visit += 1
                show(n, visit, state)
        if state["reply"]:
            print("  reply:", state["reply"].text)
        else:
            print(f"  FAILED at '{state['failed_step']}': {state['error']}")
    except GraphRecursionError:
        print(f"  STOPPED by the recursion limit ({RECURSION_LIMIT}) after {visit} node visits")
    print("  path:", " -> ".join(state["trace"]))
