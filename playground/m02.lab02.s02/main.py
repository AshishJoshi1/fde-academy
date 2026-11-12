import json
import os

import anthropic
import httpx

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]  # the lab starts the mock Meridian API for each run
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

# The tool as the model sees it: a name, a description, and a JSON Schema for its input.
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


# The tool as your code runs it: a plain function that calls the Meridian API.
def get_opportunity(opportunity_id: str) -> dict:
    r = httpx.get(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10)
    return r.json()


RUN = {"get_opportunity": get_opportunity}  # tool name -> the function that does the work

messages = [{"role": "user", "content": "What discount did procurement ask for on OPP-1042, "
                                        "and which account is it for?"}]

for turn in range(1, 6):  # a cap on turns: never loop forever
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        output_config={"effort": "low"},
        tools=TOOLS,
        messages=messages,
    )
    print(f"turn {turn}: stop_reason={response.stop_reason} blocks={[b.type for b in response.content]}")
    messages.append({"role": "assistant", "content": response.content})  # all of it, as it came back
    if response.stop_reason != "tool_use":
        break

    results = []
    for block in response.content:
        if block.type == "tool_use":
            output = RUN[block.name](**block.input)
            print(f"  ran {block.name}({json.dumps(block.input)}): {len(json.dumps(output))} characters back")
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output)})
    messages.append({"role": "user", "content": results})  # every result, in one user message

if response.stop_reason == "end_turn":
    print("answer:", "".join(b.text for b in response.content if b.type == "text"))
else:
    print("stopped without an answer: stop_reason =", response.stop_reason)
