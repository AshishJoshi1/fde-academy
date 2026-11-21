import asyncio
import json
import os
import time
from typing import Annotated, Literal, TypedDict

import anthropic
import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, ValidationError

client = anthropic.AsyncAnthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

SLOW = None        # experiments 1 and 2: "rate", "account" or "notes" makes that worker wait SLOW_S seconds first
SLOW_S = 8         # how long the slowed worker waits
TIMEOUT_S = 20     # each worker's own time limit, in seconds (experiment 2 lowers it)
HONEST = True      # experiment 3: False records a worker that timed out or failed as a pass
OPPORTUNITIES = ["OPP-1042", "OPP-1043", "OPP-1044"]

# How the three worker results combine, as data: the first outcome in this list that any worker
# reported decides the verdict. If none of them did, the verdict is "approve".
RULE = [("fail", "reject"), ("unknown", "needs_review")]


# ---- State ------------------------------------------------------------------------------------------
def merge(old, new):
    """Reducer: each worker returns {its name: result}; the merged dict keeps every worker's entry."""
    return {**(old or {}), **(new or {})}


class ReviewState(TypedDict):
    opp: str
    results: Annotated[dict, merge]   # check name -> {"outcome": pass | fail | unknown, "detail": ...}
    verdict: str | None


# ---- The three checks: each returns (outcome, detail) -------------------------------------------------
async def pause(name):
    if SLOW == name:                  # the "slow this worker" switch
        await asyncio.sleep(SLOW_S)


async def check_rate(opp):            # plain code: does every effort row have a valid rate on the start date?
    await pause("rate")
    async with httpx.AsyncClient(headers=AUTH, timeout=15) as http:
        o = (await http.get(f"{MERIDIAN}/opportunities/{opp}")).json()
        missing = []
        for row in o["effort"]:
            params = {"role": row["role"], "location": row["location"], "as_of": o["start_date"]}
            rates = (await http.get(f"{MERIDIAN}/rate-card", params=params)).json()["items"]
            if not rates:
                missing.append(f"{row['role']}/{row['location']}")
    return ("fail", "no valid rate on " + o["start_date"] + " for " + ", ".join(missing)) if missing else ("pass", "every effort row has a rate")


async def check_account(opp):         # plain code: is the deal's account in the account list?
    await pause("account")
    async with httpx.AsyncClient(headers=AUTH, timeout=15) as http:
        o = (await http.get(f"{MERIDIAN}/opportunities/{opp}")).json()
        page = 1
        while page:
            body = (await http.get(f"{MERIDIAN}/accounts", params={"page": page, "page_size": 5})).json()
            for a in body["items"]:
                if a["account_id"] == o["account_id"]:
                    return ("pass", a["legal_name"])
            page = body["next_page"]
    return ("fail", f"account {o['account_id']} is not in the account list")


class Risk(BaseModel):
    level: Literal["none", "low", "high"]
    reason: str


async def check_notes(opp):           # one model call: does the CRM note describe a risk?
    await pause("notes")
    async with httpx.AsyncClient(headers=AUTH, timeout=15) as http:
        o = (await http.get(f"{MERIDIAN}/opportunities/{opp}")).json()
    response = await client.messages.parse(
        model=MODEL, max_tokens=1024, output_config={"effort": "low"},
        system="You review a CRM note on a sales opportunity before it goes to approval. "
               "Say how risky the note makes the deal: none, low or high. Give one short reason.",
        messages=[{"role": "user", "content": o["crm_notes"]}], output_format=Risk)
    risk = response.parsed_output
    return ("fail" if risk.level == "high" else "pass", f"{risk.level}: {risk.reason}")


CHECKS = {"rate": check_rate, "account": check_account, "notes": check_notes}


# ---- The worker: one node, run once per Send ----------------------------------------------------------
async def check_node(job):            # `job` is the Send payload, not the graph state
    name, started = job["check"], time.monotonic() - RUN_START
    try:
        outcome, detail = await asyncio.wait_for(CHECKS[name](job["opp"]), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        outcome, detail = "unknown", f"timed out after {TIMEOUT_S}s"
    except (httpx.HTTPError, ValidationError, KeyError, ValueError) as exc:
        outcome, detail = "unknown", f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
    if outcome == "unknown" and not HONEST:   # experiment 3: hide the failure as a pass
        outcome = "pass"
    ended = time.monotonic() - RUN_START
    print("@@lane " + json.dumps({"kind": "lane", "opp": job["opp"], "check": name, "start": round(started, 2),
                                   "end": round(ended, 2), "outcome": outcome, "detail": detail}), flush=True)
    return {"results": {name: {"outcome": outcome, "detail": detail}}}


def fan_out(state):                   # the conditional edge: one Send per check
    return [Send("check", {"opp": state["opp"], "check": name}) for name in CHECKS]


def aggregate(state):                 # runs once, after every worker has returned
    outcomes = [state["results"].get(name, {"outcome": "unknown"})["outcome"] for name in CHECKS]
    verdict = next((v for o, v in RULE if o in outcomes), "approve")
    return {"verdict": verdict}


graph = StateGraph(ReviewState)
graph.add_node("check", check_node)
graph.add_node("aggregate", aggregate)
graph.add_conditional_edges(START, fan_out, ["check"])
graph.add_edge("check", "aggregate")
graph.add_edge("aggregate", END)
app = graph.compile()


# ---- Run the graph on each opportunity ----------------------------------------------------------------
async def main():
    global RUN_START
    for opp in OPPORTUNITIES:
        RUN_START = time.monotonic()
        final = await app.ainvoke({"opp": opp, "results": {}, "verdict": None})
        wall = time.monotonic() - RUN_START
        print("@@lane " + json.dumps({"kind": "verdict", "opp": opp, "verdict": final["verdict"], "wall": round(wall, 2)}), flush=True)
        print(f"{opp}: {final['verdict']}  ({wall:.1f}s)")
        for name in CHECKS:
            r = final["results"].get(name)
            print(f"  {name:8} {r['outcome'] if r else 'MISSING':8} {r['detail'] if r else ''}")


asyncio.run(main())
