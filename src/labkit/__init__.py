"""labkit runs *inside* a lesson process: hooks the lab gives lesson code. Standard library only.

approve(tool, tool_input) asks a human before a tool runs. In the lab page the run pauses and
the page shows Approve and Deny; run from a terminal (tools/run_live.py) it asks on the console.
"""
import json
import os
import urllib.error
import urllib.request

__version__ = "0.2.0"


def approve(tool: str, tool_input: dict, *, timeout_s: int = 60) -> tuple[bool, str]:
    """Ask a human whether `tool` may run with `tool_input`. Returns (approved, reason).

    No answer within `timeout_s` counts as a denial: the safe default when nobody is there.
    """
    url = os.environ.get("LAB_APPROVAL_URL")
    if not url:                      # no lab page: ask on the console
        answer = input(f"Approve {tool}({json.dumps(tool_input)})? [y/N] ").strip().lower()
        return answer in ("y", "yes"), "approved on the console" if answer in ("y", "yes") else "denied on the console"
    body = json.dumps({"tool": tool, "input": tool_input, "timeout_s": timeout_s}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s + 10) as resp:
            answer = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return False, f"no answer ({exc}): treated as a denial"
    return bool(answer.get("approved")), str(answer.get("reason", ""))
