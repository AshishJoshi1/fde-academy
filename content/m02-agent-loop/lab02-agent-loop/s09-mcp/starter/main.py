import asyncio
import json
import os
import sys

import anthropic
from mcp import Client, StdioServerParameters

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")

LIST_ONLY = True      # g4: True lists the server's tools and stops, no model involved. g5: False runs the agent
BREAK = "none"        # E1: "crash" or "error" makes the server fail inside a tool call
PADDING = 0           # E2: how many extra, unrelated tools the server serves

# How this client starts the server: a subprocess whose stdin and stdout carry the MCP messages.
SERVER = StdioServerParameters(
    command=sys.executable,
    args=["server.py"],
    env={**os.environ, "SERVER_BREAK": BREAK, "SERVER_PADDING": str(PADDING)},
)

QUESTION = "What discount did procurement ask for on OPP-1042, and what industry is its client in?"


async def main():
    async with Client(SERVER) as mcp:
        listed = await mcp.list_tools()  # discovery: ask the server what it offers
        print("tools:", [t.name for t in listed.tools])
        if LIST_ONLY:
            for t in listed.tools:
                print(f"  {t.name}: {t.description.splitlines()[0]}")
                print(f"    input_schema: {json.dumps(t.input_schema)}")
            return

        # An MCP tool already has a name, a description and an input schema: rename one key and
        # it is an Anthropic tool definition.
        tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in listed.tools]

        messages = [{"role": "user", "content": QUESTION}]
        for turn in range(1, 8):
            response = client.messages.create(
                model=MODEL, max_tokens=2048, output_config={"effort": "low"}, tools=tools, messages=messages,
            )
            print(f"turn {turn}: stop_reason={response.stop_reason} blocks={[b.type for b in response.content]}")
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await mcp.call_tool(block.name, block.input)  # the server runs the tool
                    text = "".join(c.text for c in result.content if c.type == "text")
                    print(f"  mcp call {block.name}({json.dumps(block.input)}): is_error={result.is_error}, {len(text)} characters back")
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": text,
                                    "is_error": result.is_error})
            messages.append({"role": "user", "content": results})

        if response.stop_reason == "end_turn":
            print("answer:", "".join(b.text for b in response.content if b.type == "text"))
        else:
            print("stopped without an answer: stop_reason =", response.stop_reason)
        print("input tokens, last call:", response.usage.input_tokens)


asyncio.run(main())
