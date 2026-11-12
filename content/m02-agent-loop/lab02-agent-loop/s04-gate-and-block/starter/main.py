import json
import os

import anthropic
import httpx

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]  # the lab starts the mock Meridian API for each run
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

TOOLS = [
    {
        "name": "get_opportunity",
        "description": "Look up one sales opportunity in the Meridian CRM by its ID, e.g. OPP-1042. "
                       "Returns its account ID, stage, requested discount, staffing and CRM notes.",
        "input_schema": {
            "type": "object",
            "properties": {"opportunity_id": {"type": "string", "description": "e.g. OPP-1042"}},
            "required": ["opportunity_id"],
        },
    },
    {
        "name": "update_opportunity",
        "description": "Change the requested discount of one opportunity in the Meridian CRM. "
                       "This WRITES to the CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "e.g. OPP-1046"},
                "requested_discount_pct": {"type": "number", "description": "the new discount, in percent"},
            },
            "required": ["opportunity_id", "requested_discount_pct"],
        },
    },
]


def get_opportunity(opportunity_id: str) -> dict:
    r = httpx.get(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10)
    if r.status_code == 404:
        raise LookupError(f"no opportunity with ID {opportunity_id}")
    if r.status_code != 200:
        raise RuntimeError(f"the Meridian API answered {r.status_code}")
    return r.json()


def update_opportunity(opportunity_id: str, requested_discount_pct: float) -> dict:
    r = httpx.patch(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10,
                    json={"requested_discount_pct": requested_discount_pct})
    return {"opportunity_id": opportunity_id, "requested_discount_pct": requested_discount_pct,
            "api_status": r.status_code}


RUN = {"get_opportunity": get_opportunity, "update_opportunity": update_opportunity}

POLICY = json.load(open("work/policy.json"))  # the tools this code refuses to run: edit work/policy.json

SYSTEM = "You help the Meridian sales-operations team review CRM opportunities."
# SYSTEM += " Never change CRM records: you are read-only."  # g2

messages = [{"role": "user", "content": "OPP-1046 asks for a 22% discount, above our 15% limit. "
                                        "Look it up and set its requested discount to 15%."}]

for turn in range(1, 6):  # a cap on turns: never loop forever
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        output_config={"effort": "low"},
        system=SYSTEM,
        tools=TOOLS,
        messages=messages,
    )
    uses = [b for b in response.content if b.type == "tool_use"]
    print(f"turn {turn}: stop_reason={response.stop_reason} tool_use blocks={len(uses)}")
    messages.append({"role": "assistant", "content": response.content})
    if response.stop_reason != "tool_use":
        break

    results = []
    for block in uses:
        if block.name in POLICY["blocked_tools"]:  # the gate: code decides, whatever the model asked
            results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                            "content": f"BLOCKED: {block.name} is not allowed by policy. Nothing was changed."})
            print(f"  {block.id}: {block.name}({json.dumps(block.input)}) -> BLOCKED by policy")
            continue
        try:
            output = RUN[block.name](**block.input)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output)})
        except Exception as e:
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": f"{type(e).__name__}: {e}", "is_error": True})
        print(f"  {block.id}: {block.name}({json.dumps(block.input)})"
              + (" -> is_error" if results[-1].get("is_error") else ""))
    messages.append({"role": "user", "content": results})

if response.stop_reason == "end_turn":
    print("answer:", "".join(b.text for b in response.content if b.type == "text"))
else:
    print("stopped without an answer: stop_reason =", response.stop_reason)
