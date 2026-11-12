import json
import os

import anthropic
import httpx

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]  # the lab starts the mock Meridian API for each run
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

# The same tool as in s02.
TOOLS = [{
    "name": "get_opportunity",
    "description": "Look up one sales opportunity in the Meridian CRM by its ID, e.g. OPP-1042. "
                   "Returns its account ID, stage, requested discount, staffing and CRM notes.",
    "input_schema": {
        "type": "object",
        "properties": {"opportunity_id": {"type": "string", "description": "e.g. OPP-1042"}},
        "required": ["opportunity_id"],
    },
}]


def get_opportunity(opportunity_id: str) -> dict:
    r = httpx.get(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10)
    if r.status_code == 404:  # an error message written for the model: no URL, no token
        raise LookupError(f"no opportunity with ID {opportunity_id}")
    if r.status_code != 200:
        raise RuntimeError(f"the Meridian API answered {r.status_code}")
    return r.json()


RUN = {"get_opportunity": get_opportunity}  # tool name -> the function that does the work

messages = [{"role": "user", "content": "Which of OPP-1042, OPP-1046 and OPP-1048 has the largest "
                                        "requested discount, and which account is each for?"}]

for turn in range(1, 6):  # a cap on turns: never loop forever
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        output_config={"effort": "low"},
        tools=TOOLS,
        # tool_choice={"type": "auto", "disable_parallel_tool_use": True},  # E1
        messages=messages,
    )
    uses = [b for b in response.content if b.type == "tool_use"]
    print(f"turn {turn}: stop_reason={response.stop_reason} tool_use blocks={len(uses)}")
    messages.append({"role": "assistant", "content": response.content})  # all of it, as it came back
    if response.stop_reason != "tool_use":
        break

    results = []
    for block in uses:  # run every tool the model asked for, then send all the results at once
        try:
            output = RUN[block.name](**block.input)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output)})
        except Exception as e:  # a failed tool still gets a result: never drop one
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": f"{type(e).__name__}: {e}", "is_error": True})
        print(f"  {block.id}: {block.name}({json.dumps(block.input)})"
              + (" -> is_error" if results[-1].get("is_error") else ""))
    messages.append({"role": "user", "content": results})  # every result, in ONE user message

if response.stop_reason == "end_turn":
    print("answer:", "".join(b.text for b in response.content if b.type == "text"))
else:
    print("stopped without an answer: stop_reason =", response.stop_reason)
