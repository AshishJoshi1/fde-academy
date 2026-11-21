import json
import os
from typing import Literal, TypedDict

import anthropic
import httpx
from labkit import approve
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

THREAD = "run-1"       # the name of this run's saved history: a new name is a fresh run, the same name resumes
CRASH_AT = None        # step g4: "respond" kills the process when ticket 1 reaches that node
PATCH_FIRST = False    # experiment 1: True sends the change BEFORE interrupt(), so a resume sends it twice
DB = "checkpoints.db"  # the checkpoint file, next to this code: it outlives the process

TICKETS = [
    "Please set the discount on OPP-1044 to 15%. Finance will sign off later.",
    "Is OPP-1047 still at proposal stage? Our start date moved and I need to know where it stands.",
]


# ---- Typed hand-offs (as in lessons 10 and 13) ------------------------------------------------------
class Classification(BaseModel):
    category: Literal["discount_question", "status_question", "change_request"]
    opportunity_id: str
    discount_pct: float | None  # the discount the ticket asks for, or None


class Reply(BaseModel):
    text: str


# ---- The state: every key must be plain data, because a checkpoint writes it to disk ----------------
class TicketState(TypedDict, total=False):
    n: int                  # which ticket this is
    ticket: str
    classification: dict | None
    facts: dict | None
    approved: bool | None   # None when no approval was needed
    reply: str | None


def emit(**record):
    print("@@ckpt " + json.dumps(record), flush=True)  # the lab's Checkpoints panel reads this line


def enter(name, state):
    """Called first in every node: tell the panel the node started, and crash if asked to."""
    emit(e="node", n=state["n"], node=name)
    if CRASH_AT == name and state["n"] == 1:
        emit(e="crash", n=1, node=name)
        os._exit(1)  # no cleanup, no exception handler: what a killed process looks like


def ask(system, user, schema):
    return client.messages.parse(
        model=MODEL, max_tokens=2048, output_config={"effort": "low"},
        system=system, messages=[{"role": "user", "content": user}], output_format=schema).parsed_output


# ---- The nodes ----------------------------------------------------------------------------------------
def classify_node(state):
    enter("classify", state)
    c = ask("Classify a customer ticket about a sales opportunity. Category: a question about the requested "
            "discount, a question about the stage or start date, or a request to change a record. Give the "
            "opportunity ID it names, and the discount percentage the ticket asks for (null if none).",
            state["ticket"], Classification)
    if c.opportunity_id not in state["ticket"]:
        raise ValueError(f"opportunity_id {c.opportunity_id!r} is not in the ticket")
    return {"classification": c.model_dump()}


def enrich_node(state):  # plain code: no model, no tokens
    enter("enrich", state)
    r = httpx.get(f"{MERIDIAN}/opportunities/{state['classification']['opportunity_id']}", headers=AUTH, timeout=10)
    r.raise_for_status()
    o = r.json()
    return {"facts": {k: o[k] for k in ("opportunity_id", "stage", "start_date", "requested_discount_pct", "currency")}}


def send_change(state, change):
    r = httpx.patch(f"{MERIDIAN}/opportunities/{change['opportunity_id']}", json=change, headers=AUTH, timeout=10)
    r.raise_for_status()
    emit(e="patch", n=state["n"], change=change)  # the side effect: a write to the CRM


def apply_node(state):
    enter("apply", state)
    c = state["classification"]
    if c["category"] != "change_request" or c["discount_pct"] is None:
        return {"approved": None}  # nothing to change, nothing to approve
    change = {"opportunity_id": c["opportunity_id"], "requested_discount_pct": c["discount_pct"]}
    if PATCH_FIRST:
        send_change(state, change)
    ok = interrupt({"action": "change the requested discount", **change})  # the run stops here, and is saved
    if ok and not PATCH_FIRST:
        send_change(state, change)
    return {"approved": bool(ok)}


def respond_node(state):
    enter("respond", state)
    pct = state["classification"]["discount_pct"]
    note = f"The change was applied: the requested discount is now {pct:g}%." if state["approved"] else "Nothing was changed."
    assert state["approved"] in (True, None)  # a denial went to `declined`, not here
    text = ask("Write a short, polite reply to the customer, two sentences at most. Use ONLY these facts: "
               + json.dumps(state["facts"]) + ". " + note, state["ticket"], Reply).text
    return {"reply": text}


def declined_node(state):  # no model call: a fixed reply when a person said no
    enter("declined", state)
    return {"reply": "A colleague reviewed the request and it was not approved, so nothing was changed."}


def after_apply(state):
    return "declined" if state["approved"] is False else "respond"


graph = StateGraph(TicketState)
graph.add_node("classify", classify_node)
graph.add_node("enrich", enrich_node)
graph.add_node("apply", apply_node)
graph.add_node("respond", respond_node)
graph.add_node("declined", declined_node)
graph.add_edge(START, "classify")
graph.add_edge("classify", "enrich")
graph.add_edge("enrich", "apply")
graph.add_conditional_edges("apply", after_apply, {"respond": "respond", "declined": "declined"})
graph.add_edge("respond", END)
graph.add_edge("declined", END)


# ---- Run: start, resume or skip each ticket, and ask a person whenever the graph stops --------------
def run_until_done(app, graph_input, cfg):
    result = app.invoke(graph_input, cfg, durability="sync")  # "sync": each checkpoint is on disk before the next node starts
    while result.get("__interrupt__"):  # the graph stopped at interrupt(): ask, then resume with the answer
        payload = result["__interrupt__"][0].value
        emit(e="interrupt", n=cfg["configurable"]["n"], payload=payload)
        ok, why = approve("set_discount", payload)
        emit(e="answer", n=cfg["configurable"]["n"], approved=bool(ok))
        print(f"  a person said: {'approve' if ok else 'deny'} ({why})")
        result = app.invoke(Command(resume=ok), cfg, durability="sync")
    return result


def saved(app, cfg):
    """The checkpoints for this thread, oldest first: one per finished node, plus one for the input."""
    rows = [{"step": s.metadata["step"], "next": list(s.next),
             "has": [k for k in ("classification", "facts", "approved", "reply") if s.values.get(k) is not None]}
            for s in app.get_state_history(cfg)]
    return rows[::-1]


with SqliteSaver.from_conn_string(DB) as saver:
    app = graph.compile(checkpointer=saver)
    for n, ticket in enumerate(TICKETS, 1):
        cfg = {"configurable": {"thread_id": f"{THREAD}-ticket-{n}", "n": n}}
        print(f"ticket {n}: {ticket}")
        snapshot = app.get_state(cfg)
        if snapshot.next:  # saved, but not finished: pick up where it stopped
            emit(e="resume", n=n, next=list(snapshot.next))
            print(f"  resuming at: {', '.join(snapshot.next)}")
            result = run_until_done(app, None, cfg)
        elif snapshot.values:  # saved and finished: nothing to run
            emit(e="done_before", n=n)
            print("  already finished, nothing to run")
            result = snapshot.values
        else:
            result = run_until_done(app, {"n": n, "ticket": ticket}, cfg)
        emit(e="saved", n=n, thread=cfg["configurable"]["thread_id"], checkpoints=saved(app, cfg))
        print("  reply:", result["reply"])
