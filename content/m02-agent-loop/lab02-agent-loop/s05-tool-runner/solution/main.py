import json
import os

import anthropic
import httpx
from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from labkit import approve  # the lab's hook: pauses the run until you click Approve or Deny

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]  # the lab starts the mock Meridian API for each run
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

ASK_FIRST = set()  # tools that pause for a human before they run. g4: try {"update_opportunity"}


def ask_first(tool: str, tool_input: dict) -> None:
    """Return if the tool may run; raise ToolError (the runner sends it back as is_error) if not."""
    if tool in ASK_FIRST:
        approved, reason = approve(tool, tool_input)
        if not approved:
            raise ToolError(f"DENIED: {reason}. Nothing was changed.")


@beta_tool
def get_opportunity(opportunity_id: str) -> str:
    """Look up one sales opportunity in the Meridian CRM by its ID, e.g. OPP-1042.
    Returns its account ID, stage, requested discount, staffing and CRM notes.

    Args:
        opportunity_id: e.g. OPP-1042
    """
    ask_first("get_opportunity", {"opportunity_id": opportunity_id})
    r = httpx.get(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10)
    if r.status_code != 200:
        raise ToolError(f"the Meridian API answered {r.status_code}")
    return r.text


@beta_tool
def update_opportunity(opportunity_id: str, requested_discount_pct: float) -> str:
    """Change the requested discount of one opportunity in the Meridian CRM. This WRITES to the CRM.

    Args:
        opportunity_id: e.g. OPP-1046
        requested_discount_pct: the new discount, in percent
    """
    ask_first("update_opportunity", {"opportunity_id": opportunity_id,
                                     "requested_discount_pct": requested_discount_pct})
    r = httpx.patch(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10,
                    json={"requested_discount_pct": requested_discount_pct})
    return json.dumps({"opportunity_id": opportunity_id, "requested_discount_pct": requested_discount_pct,
                       "api_status": r.status_code})


runner = client.beta.messages.tool_runner(
    model=MODEL,
    max_tokens=2048,
    max_iterations=6,  # a cap on model calls: never loop forever
    thread=False,  # resend the whole history on every call, as your s02 loop did (see g2)
    output_config={"effort": "low"},
    system="You help the Meridian sales-operations team review CRM opportunities.",
    tools=[get_opportunity, update_opportunity],
    messages=[{"role": "user", "content": "OPP-1046 asks for a 22% discount, above our 15% limit. "
                                          "Look it up and set its requested discount to 15%."}],
)

for call, message in enumerate(runner, 1):  # one pass per model call; the runner runs the tools after each pass
    uses = [b for b in message.content if b.type == "tool_use"]
    print(f"call {call}: stop_reason={message.stop_reason} tool_use blocks={len(uses)}")
    for block in uses:
        print(f"  asked for {block.name}({json.dumps(block.input)}), not run yet")

if message.stop_reason == "end_turn":
    print("answer:", "".join(b.text for b in message.content if b.type == "text"))
else:
    print("stopped without an answer: stop_reason =", message.stop_reason)
