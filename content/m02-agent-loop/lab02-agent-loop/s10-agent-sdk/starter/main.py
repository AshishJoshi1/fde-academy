import asyncio
import json
import os

import httpx
from claude_agent_sdk import (
    AgentDefinition, AssistantMessage, ClaudeAgentOptions, HookMatcher, ResultMessage, TextBlock,
    ToolResultBlock, ToolUseBlock, UserMessage, create_sdk_mcp_server, query, tool,
)

MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")
MERIDIAN = os.environ["MERIDIAN_API_URL"]  # the lab starts the mock Meridian API for each run
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}

BLOCK = False      # g6, E1: True adds a hook that refuses update_opportunity
SUBAGENT = False   # g7: True lets the agent hand a lookup to a subagent
WRITE = False      # E1: True asks the agent to change a record instead of only reading
QUESTION = ("OPP-1046 asks for a 22% discount, above our 15% limit. Set it to 15% now." if WRITE else
            "What discount did procurement ask for on OPP-1042, and what industry is its client in?")
if SUBAGENT:
    QUESTION += " Use the lookup subagent to find the account's details."


# Your tools: plain async functions. The decorator gives each a name, a description and an input schema.
@tool("get_opportunity", "Look up one sales opportunity in the Meridian CRM by its ID, e.g. OPP-1042. "
      "Returns its account ID, stage, requested discount, staffing and CRM notes.", {"opportunity_id": str})
async def get_opportunity(args):
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{MERIDIAN}/opportunities/{args['opportunity_id']}", headers=AUTH, timeout=10)
    return {"content": [{"type": "text", "text": json.dumps(r.json())}]}


@tool("get_account", "Look up one client account in the Meridian CRM by its ID, e.g. ACC-017. "
      "Returns the company name, industry, region and its past deals.", {"account_id": str})
async def get_account(args):
    async with httpx.AsyncClient() as http:
        page = 1
        while page:
            data = (await http.get(f"{MERIDIAN}/accounts", params={"page": page}, headers=AUTH, timeout=10)).json()
            for account in data["items"]:
                if account["account_id"] == args["account_id"]:
                    return {"content": [{"type": "text", "text": json.dumps(account)}]}
            page = data["next_page"]
    return {"content": [{"type": "text", "text": f"no account {args['account_id']}"}], "is_error": True}


@tool("update_opportunity", "Change the requested discount of one opportunity in the Meridian CRM. "
      "This WRITES to the CRM.", {"opportunity_id": str, "requested_discount_pct": float})
async def update_opportunity(args):
    async with httpx.AsyncClient() as http:
        r = await http.patch(f"{MERIDIAN}/opportunities/{args['opportunity_id']}", headers=AUTH, timeout=10,
                             json={"requested_discount_pct": args["requested_discount_pct"]})
    return {"content": [{"type": "text", "text": f"updated, api status {r.status_code}"}]}


async def refuse_writes(input_data, tool_use_id, context):
    """A PreToolUse hook: the SDK calls it before every matching tool call, and a deny stops the call."""
    print(f"  hook: {input_data['tool_name']} {json.dumps(input_data['tool_input'])} -> deny")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": "this agent is read-only: CRM writes are refused"}}


meridian = create_sdk_mcp_server(name="meridian", tools=[get_opportunity, get_account, update_opportunity])

options = ClaudeAgentOptions(
    model=MODEL,
    effort="low",
    system_prompt="You help the Meridian sales-operations team review CRM opportunities.",
    mcp_servers={"meridian": meridian},
    tools=["Agent"] if SUBAGENT else [],  # the built-in tools: none, so only your Meridian tools exist
    allowed_tools=["mcp__meridian__*"] + (["Agent"] if SUBAGENT else []),  # run without asking
    agents={"lookup": AgentDefinition(description="Looks up one CRM record and reports it in one line.",
                                      prompt="Look up what you are asked and answer in one line.",
                                      tools=["mcp__meridian__get_opportunity", "mcp__meridian__get_account"])}
    if SUBAGENT else None,
    hooks={"PreToolUse": [HookMatcher(matcher="mcp__meridian__update_opportunity", hooks=[refuse_writes])]}
    if BLOCK else None,
    setting_sources=[],  # ignore any CLAUDE.md or settings on this machine
    max_turns=8,
)


async def main():
    async for message in query(prompt=QUESTION, options=options):
        if isinstance(message, AssistantMessage):
            who = "  [subagent]" if message.parent_tool_use_id else ""  # set on messages from inside a subagent
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"{who}  tool_use {block.name}({json.dumps(block.input)[:150]})")
                elif isinstance(block, TextBlock):
                    print("assistant:", block.text)
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    print(f"  tool_result is_error={block.is_error}")
        elif isinstance(message, ResultMessage):
            print(f"done: {message.subtype}, {message.num_turns} turns, SDK cost estimate ${message.total_cost_usd:.4f}")


asyncio.run(main())
