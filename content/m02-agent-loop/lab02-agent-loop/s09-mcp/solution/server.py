"""A small MCP server for the Meridian CRM. A client starts it and talks to it over stdin and stdout."""
import os

import logging

import httpx
from mcp.server.mcpserver import MCPServer

MERIDIAN = os.environ["MERIDIAN_API_URL"]
AUTH = {"Authorization": f"Bearer {os.environ['MERIDIAN_API_TOKEN']}"}
BREAK = os.getenv("SERVER_BREAK", "none")      # E1: "crash" or "error"
PADDING = int(os.getenv("SERVER_PADDING", "0"))  # E2: how many extra, unrelated tools to serve

logging.getLogger("httpx").setLevel(logging.WARNING)  # keep the server's stderr quiet

mcp = MCPServer("meridian")


@mcp.tool()
def get_opportunity(opportunity_id: str) -> dict:
    """Look up one sales opportunity in the Meridian CRM by its ID, e.g. OPP-1042.
    Returns its account ID, stage, requested discount, staffing and CRM notes."""
    if BREAK == "crash":
        os._exit(1)  # the server process dies in the middle of the call
    if BREAK == "error":
        raise RuntimeError("the CRM database is down")
    return httpx.get(f"{MERIDIAN}/opportunities/{opportunity_id}", headers=AUTH, timeout=10).json()


@mcp.tool()
def get_account(account_id: str) -> dict:
    """Look up one client account in the Meridian CRM by its ID, e.g. ACC-017.
    Returns the company name, industry, region and its past deals."""
    page = 1
    while page:
        data = httpx.get(f"{MERIDIAN}/accounts", params={"page": page}, headers=AUTH, timeout=10).json()
        for account in data["items"]:
            if account["account_id"] == account_id:
                return account
        page = data["next_page"]
    return {"error": f"no account {account_id}"}


# g7: uncomment to add a tool. The client code does not change.
# @mcp.tool()
# def get_day_rate(role: str, location: str) -> dict:
#     """Look up the day rate for a role (e.g. R-ARCH) in a location (e.g. UK) from the rate card."""
#     return httpx.get(f"{MERIDIAN}/rate-card", params={"role": role, "location": location}, headers=AUTH, timeout=10).json()


def _padding_tool(n):
    def tool(text: str) -> str:
        return text
    tool.__name__ = f"unrelated_tool_{n}"
    tool.__doc__ = f"Unrelated tool number {n}. Echoes the text it is given. Not useful for Meridian questions."
    return tool


for i in range(PADDING):
    mcp.tool()(_padding_tool(i))

if __name__ == "__main__":
    mcp.run("stdio")
