"""Check a locally running AgentCore agent container. Deploy-ready, not deployed.

    uv run python deploy/aws/agent_check.py http://127.0.0.1:18080

The container must run with AGENT_MODEL_MODE=scripted: the real BedrockProvider builds
each request, and an in-process mock transport answers it, so no AWS call is made.
The check proves the wiring (HTTP contract, agent loop, MCP over HTTP, Bedrock request
shape). The classification itself is scripted, not model output.
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlparse

import httpx

PRODUCT = (
    "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, "
    "two shoulder straps and a polyester lining."
)
HTS10 = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def main() -> None:
    base = sys.argv[1].rstrip("/")
    if urlparse(base).hostname not in {"127.0.0.1", "localhost"}:
        fail("agent_check.py only runs against a local container")

    bad = httpx.post(f"{base}/invocations", json={"description": ""}, timeout=30)
    if bad.status_code != 400:
        fail(f"empty description should be 400, got {bad.status_code}")
    print("  ok  /invocations rejects an empty description (400)")

    r = httpx.post(
        f"{base}/invocations", json={"description": PRODUCT, "item_id": "local-check"}, timeout=180
    )
    if r.status_code != 200:
        fail(f"/invocations returned {r.status_code}: {r.text[:300]}")
    d = r.json()
    c = d.get("classification") or {}
    if d.get("model_mode") != "scripted":
        fail(f"container is not in scripted mode: {d.get('model_mode')}")
    if not HTS10.match(c.get("hts10", "")):
        fail(f"no 10-digit code in the answer: {c.get('hts10')!r}")
    needed = {"hts_search", "cross_search", "ruling_status"}
    if not needed <= set(d.get("tools_used", [])):
        fail(f"agent did not call {needed} over MCP: {d.get('tools_used')}")
    s = d.get("scripted_bedrock_requests") or {}
    if s.get("model_ids") != ["anthropic.claude-sonnet-5"]:
        fail(f"unexpected Bedrock model ids: {s.get('model_ids')}")
    if not any(h.startswith("bedrock-mantle.") for h in s.get("hosts", [])):
        fail(f"requests were not built for the Bedrock endpoint: {s.get('hosts')}")
    if not s.get("system_cache_breakpoint"):
        fail("system prompt has no cache_control breakpoint")
    if not s.get("structured_output"):
        fail("requests do not ask for structured output (output_config.format)")
    print(f"  ok  /invocations -> {c['hts10']} in {d.get('turns')} turns, tools {d.get('tools_used')}")
    print(f"  ok  Bedrock requests: {json.dumps(s)}")
    print("agent container check passed (scripted model, not a real classification)")


if __name__ == "__main__":
    main()
