import json
import os

import anthropic

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")

STRICT = False  # g5: set it to True and run again

UPDATE_TOOL = {
    "name": "update_opportunity",
    "description": "Set the requested discount of one Meridian CRM opportunity, with the reason for it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "opportunity_id": {"type": "string", "description": "e.g. OPP-1046"},
            "requested_discount_pct": {"type": "integer", "description": "the new discount, in whole percent"},
            "reason": {"type": "string", "enum": ["policy_limit", "customer_request", "manager_approved"]},
        },
        "required": ["opportunity_id", "requested_discount_pct", "reason"],
        "additionalProperties": False,
    },
}
if STRICT:
    UPDATE_TOOL["strict"] = True  # the model's input is then constrained to match the schema

ASKS = [  # messy requests: each one tempts the model to bend the schema
    "Set OPP-1046 to 12.5%. Reason: policy_limit.",
    "Give OPP-1046 a third off. Customer asked for it.",
    "OPP-1046: seven and a half percent, manager approved.",
    "Change OPP-1046's discount. I don't remember the number. Reason: policy_limit.",
    "Set OPP-1046 to 15% for policy_limit, and also mark its stage Closed Won.",
    "OPP-1046: 15 percent, manager approved it, add a note that Dana signed off.",
    "Set OPP-1046 to 14.9%, and say in the reason that it is the end-of-quarter push.",
    "Set OPP-1046 to 10.5%. The reason is that we want to win the deal.",
]


def problems(tool_input: dict) -> list[str]:
    """What is wrong with this input, judged against the schema above."""
    schema = UPDATE_TOOL["input_schema"]
    found = [f"missing {k}" for k in schema["required"] if k not in tool_input]
    found += [f"unexpected {k}" for k in tool_input if k not in schema["properties"]]
    for key, spec in schema["properties"].items():
        if key not in tool_input:
            continue
        value = tool_input[key]
        if spec["type"] == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            found.append(f"{key}={value!r} is {type(value).__name__}, not an integer")
        if key == "requested_discount_pct" and isinstance(value, int) and not 0 <= value <= 100:
            found.append(f"{key}={value} is outside 0 to 100")  # strict can't express min/max: check ranges here
        if spec["type"] == "string" and not isinstance(value, str):
            found.append(f"{key} is not a string")
        if "enum" in spec and value not in spec["enum"]:
            found.append(f"{key}={value!r} not in the enum")
    return found


bad = 0
for ask in ASKS:  # the fuzzer: one model call per messy ask, and we only look at the tool input
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},
        system="You update Meridian CRM opportunities. Always answer with a call to the update_opportunity tool, never with text.",
        tools=[UPDATE_TOOL],
        messages=[{"role": "user", "content": ask}],
    )
    uses = [b for b in response.content if b.type == "tool_use"]
    if not uses:
        print(f"{ask!r}\n  no tool call: stop_reason={response.stop_reason}")
        continue
    wrong = problems(uses[0].input)
    bad += bool(wrong)
    print(f"{ask!r}\n  input={json.dumps(uses[0].input)}\n  {'PROBLEMS: ' + '; '.join(wrong) if wrong else 'valid'}")

print(f"\n{bad} of {len(ASKS)} tool inputs broke the schema (strict={STRICT})")
