import os
from collections import Counter

import anthropic

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")

CLEAR = True       # g5: True swaps in the rewritten tools
REPEAT = 4          # g4: how many times each ask is run
RECOVERY = False    # g6: after a wrong pick, answer with an error and see whether the model recovers
HELPFUL = False     # g6: the error says what to do instead
MORE_TOOLS = False  # g7: nine more tools


def tool(name, description, **params):  # params: key = description of that string argument
    props = {key: {"type": "string", "description": text} for key, text in params.items()}
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}}


VAGUE = [
    tool("get_info", "Gets information.", id="the id"),
    tool("get_details", "Gets details.", id="the id"),
    tool("lookup", "Looks things up.", id="the id"),
]
CLEAR_TOOLS = [
    tool("get_opportunity", "Fetch one CRM opportunity (a deal): stage, start date, requested discount, notes. Not for company data.",
         opportunity_id="e.g. OPP-1042"),
    tool("get_account", "Fetch one customer account (a company): legal name, industry, contracting region, past deals. Not for open opportunities.",
         account_id="e.g. ACC-001"),
    tool("get_day_rate", "Fetch the day rate of one consulting role in one location, from the rate card.",
         role="e.g. R-ARCH", location="e.g. UK"),
]
DECOYS = [
    tool("get_contract", "Fetch a signed contract: term, renewal date, signatories.", contract_id="e.g. CON-210"),
    tool("get_invoice", "Fetch one invoice: amount, due date, paid or open.", invoice_id="e.g. INV-5510"),
    tool("get_contact", "Fetch a person at a customer: title, email, phone.", contact_id="e.g. PER-31"),
    tool("get_quote", "Fetch a priced quote that was sent to a customer.", quote_id="e.g. Q-778"),
    tool("get_product", "Fetch one product from the service catalogue.", sku="e.g. SVC-CLOUD"),
    tool("get_territory", "Fetch a sales territory and its owner.", territory="e.g. DACH"),
    tool("get_forecast", "Fetch the revenue forecast of one quarter.", quarter="e.g. 2026-Q4"),
    tool("get_activity", "Fetch a logged call or meeting.", activity_id="e.g. ACT-90"),
    tool("get_note", "Fetch a free-text note attached to a record.", note_id="e.g. NOTE-12"),
]
TOOLS = CLEAR_TOOLS if CLEAR else VAGUE
if MORE_TOOLS:
    TOOLS = TOOLS + DECOYS

# What YOUR code does behind each name. The model never sees this table.
MEANS = {"get_info": "opportunity", "get_details": "account", "lookup": "day_rate",
         "get_opportunity": "opportunity", "get_account": "account", "get_day_rate": "day_rate"}
ASKS = [
    ("What stage is opportunity OPP-1042 in?", "opportunity"),
    ("Which contracting region is account ACC-001 in?", "account"),
    ("What is the day rate of an R-ARCH in the UK?", "day_rate"),
]


def error_for(name, kind):
    if not HELPFUL:
        return "Error: not found."
    right = next(n for n, k in MEANS.items() if k == kind and n in [t["name"] for t in TOOLS])
    return f"Error: {name} does not hold that. A {kind} question goes to {right}."


def ask_model(messages):
    return client.messages.create(
        model=MODEL,
        max_tokens=512,
        output_config={"effort": "low"},
        system="You answer questions about Meridian CRM. Use a tool to look things up.",
        tools=TOOLS,
        messages=messages,
    )


wrong = []  # (ask, kind, response) of every first pick that went to the wrong tool
for ask, kind in ASKS:
    picks = Counter()
    for _ in range(REPEAT):
        response = ask_model([{"role": "user", "content": ask}])
        uses = [b for b in response.content if b.type == "tool_use"]
        name = uses[0].name if uses else "(no tool)"
        picks[name] += 1
        if MEANS.get(name) != kind:
            wrong.append((ask, kind, response))
    print(f"{ask!r} wants {kind}\n  picks: " + ", ".join(f"{n} x{c}" for n, c in picks.most_common()))

total = len(ASKS) * REPEAT
print(f"\nwrong tool: {len(wrong)} of {total} (CLEAR={CLEAR}, {len(TOOLS)} tools)")

if RECOVERY:  # the model got an error for its pick: does it try the right tool next?
    fixed = 0
    for ask, kind, response in wrong[:4]:
        uses = [b for b in response.content if b.type == "tool_use"]
        if not uses:
            continue
        results = [{"type": "tool_result", "tool_use_id": b.id, "is_error": True, "content": error_for(b.name, kind)} for b in uses]
        again = ask_model([{"role": "user", "content": ask}, {"role": "assistant", "content": response.content},
                           {"role": "user", "content": results}])
        second = [b.name for b in again.content if b.type == "tool_use"]
        good = bool(second) and MEANS.get(second[0]) == kind
        fixed += good
        print(f"{ask!r}: first {uses[0].name}, then {second[0] if second else '(no tool)'} -> {'recovered' if good else 'still wrong'}")
    print(f"recovered: {fixed} of {len(wrong[:4])} (HELPFUL={HELPFUL})")
