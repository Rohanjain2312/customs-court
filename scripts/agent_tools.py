"""Command-line access to the eight TariffAgent tools, for an agent working in a shell.

Talks to a running TariffAgent MCP server over Streamable HTTP (start it with
`uv run tariffagent-mcp --transport http --port 8765 --redact-eval`, so evaluation
rulings are hidden) and prints the same compact JSON the model sees in the harness,
cut at 6,000 characters.

    python scripts/agent_tools.py hts_search '{"text": "leather handbag"}'
    python scripts/agent_tools.py hts_navigate '{"code": "4202.21"}'
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

URL = os.environ.get("TA_MCP_URL", "http://127.0.0.1:8765/mcp")
MAX = 6000
ALLOWED = {
    "hts_search",
    "hts_navigate",
    "get_notes",
    "get_gri",
    "cross_search",
    "get_ruling",
    "ruling_status",
    "hts_revision_diff",
}


def call(name: str, args: dict) -> str:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    )
    req = urllib.request.Request(
        URL,
        data=body.encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read().decode())["result"]
    if res.get("isError"):
        return "Tool error: " + "".join(c.get("text", "") for c in res.get("content", []))[:500]
    s = json.dumps(res.get("structuredContent"), ensure_ascii=False, separators=(",", ":"))
    return s[:MAX] + '..."[truncated: call again with offset or a narrower query]' if len(s) > MAX else s


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ALLOWED:
        sys.exit(f"usage: agent_tools.py <{'|'.join(sorted(ALLOWED))}> '<json args>'")
    print(call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}))
