"""Smoke test: classify 5 fixed products against a deployed TariffAgent. Deploy-ready, not deployed.

Two parts, each optional:

MCP part (no model calls): for every product call hts_search and cross_search on the
MCP endpoint and report whether the expected chapter shows up among the candidates.

    python deploy/smoke_test.py --mcp-url http://127.0.0.1:18000/mcp --mcp-auth none
    # AWS, through the AgentCore Gateway (SigV4, tool names carry the target prefix):
    python deploy/smoke_test.py --mcp-url "$GATEWAY_URL" --mcp-auth sigv4 --tool-prefix "tariffagent-mcp___"
    # GCP Cloud Run (Google ID token; the caller needs roles/run.invoker):
    python deploy/smoke_test.py --mcp-url "$RUN_URL/mcp" --mcp-auth google-id-token

Agent part (calls Claude, so it bills): send each product to the deployed agent and
check that a 10-digit code comes back.

    # AWS AgentCore Runtime, IAM inbound auth (or --agent-auth bearer with AGENT_BEARER_TOKEN):
    python deploy/smoke_test.py --agent-url "$AGENT_INVOKE_URL" --agent-auth sigv4
    # GCP Agent Runtime (run with deploy/gcp/.venv/bin/python, needs the vertexai SDK):
    python deploy/smoke_test.py --vertex-agent "projects/P/locations/L/reasoningEngines/ID"

Any non-local target requires I_ACCEPT_CLOUD_COSTS=yes. Local runs (127.0.0.1) do not.
Only the MCP part has been run, against the local containers. The agent part and the
remote auth paths are written against the docs and have not been run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

PRODUCTS = [
    {
        "id": "handbag",
        "description": "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, "
        "two shoulder straps and a polyester lining.",
        "chapter": "42",
    },
    {
        "id": "tshirt",
        "description": "Men's short-sleeved T-shirt, knitted, 100% cotton jersey, crew neck, no pockets.",
        "chapter": "61",
    },
    {
        "id": "sneaker",
        "description": "Athletic running shoe with an outer sole of rubber and an upper of textile mesh, "
        "lace closure, for adults.",
        "chapter": "64",
    },
    {
        "id": "mug",
        "description": "Coffee mug of porcelain, 350 ml, with a handle, for household use.",
        "chapter": "69",
    },
    {
        "id": "battery",
        "description": "Rechargeable lithium-ion battery pack, 11.1 V, 5000 mAh, for a laptop computer.",
        "chapter": "85",
    },
]
HTS10 = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def guard(url: str) -> None:
    host = urlparse(url).hostname or url
    if host not in LOCAL_HOSTS and os.environ.get("I_ACCEPT_CLOUD_COSTS") != "yes":
        fail(
            f"{host} is not local. Calls to a deployed endpoint bill. "
            "Set I_ACCEPT_CLOUD_COSTS=yes to run against it on purpose."
        )


def _region_from(url: str) -> str:
    m = re.search(r"bedrock-agentcore\.([a-z0-9-]+)\.amazonaws\.com", url)
    return m.group(1) if m else os.environ.get("AWS_REGION", "us-east-1")


# ---- MCP part -----------------------------------------------------------------


def mcp_http_client(url: str, auth_mode: str):
    import httpx2

    headers = {"User-Agent": "tariffagent-smoke/0.1"}
    auth = None
    if auth_mode == "sigv4":
        sys.path.insert(0, str(Path(__file__).parent / "aws"))
        from agentcore_agent.sigv4 import SigV4Auth

        auth = SigV4Auth(_region_from(url))
    elif auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {os.environ['MCP_BEARER_TOKEN']}"
    elif auth_mode == "google-id-token":
        import google.auth.transport.requests
        import google.oauth2.id_token

        p = urlparse(url)
        audience = f"{p.scheme}://{p.netloc}"
        token = google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)
        headers["Authorization"] = f"Bearer {token}"
    elif auth_mode != "none":
        fail(f"unknown --mcp-auth {auth_mode}")
    return httpx2.AsyncClient(headers=headers, auth=auth, timeout=60)


async def mcp_part(url: str, auth_mode: str, prefix: str) -> int:
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    misses = 0
    transport = streamable_http_client(url, http_client=mcp_http_client(url, auth_mode))
    async with Client(transport) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        for tool in ("hts_search", "cross_search"):
            if f"{prefix}{tool}" not in names:
                fail(f"{prefix}{tool} is not listed by the server: {sorted(names)}")
        print(f"MCP {url}: {len(names)} tools listed")
        for p in PRODUCTS:
            t0 = time.perf_counter()
            hs = await client.call_tool(f"{prefix}hts_search", {"text": p["description"], "limit": 8})
            cs = await client.call_tool(f"{prefix}cross_search", {"query": p["description"], "limit": 3})
            ms = int((time.perf_counter() - t0) * 1000)
            if hs.is_error or cs.is_error:
                fail(f"{p['id']}: tool error {hs.content if hs.is_error else cs.content}")
            hits = (hs.structured_content or {}).get("hits", [])
            if not hits:
                fail(f"{p['id']}: hts_search returned no candidates")
            codes = [h.get("code", "") for h in hits]
            chapters = {re.sub(r"\D", "", c)[:2] for c in codes}
            found = p["chapter"] in chapters
            misses += 0 if found else 1
            rulings = [h.get("id") for h in (cs.structured_content or {}).get("hits", [])]
            print(
                f"  {p['id']:8s} {'ok  ' if found else 'MISS'} chapter {p['chapter']} "
                f"top {codes[:3]} rulings {rulings} ({ms} ms)"
            )
    print(f"MCP part done: expected chapter among candidates for {len(PRODUCTS) - misses}/{len(PRODUCTS)}")
    return misses


# ---- Agent part (bills) ------------------------------------------------------------


def _sigv4_headers(url: str, body: bytes, headers: dict) -> dict:
    import botocore.session
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    creds = botocore.session.Session().get_credentials()
    if creds is None:
        fail("no AWS credentials for SigV4")
    req = AWSRequest(method="POST", url=url, data=body, headers=headers)
    SigV4Auth(creds.get_frozen_credentials(), "bedrock-agentcore", _region_from(url)).add_auth(req)
    return dict(req.headers.items())


def agentcore_part(url: str, auth_mode: str) -> int:
    import httpx

    bad = 0
    for p in PRODUCTS:
        body = json.dumps({"description": p["description"], "item_id": f"smoke-{p['id']}"}).encode()
        headers = {
            "Content-Type": "application/json",
            # The runtime session id must be at least 33 characters.
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": f"smoke-{uuid.uuid4().hex}",
        }
        if auth_mode == "sigv4":
            headers = _sigv4_headers(url, body, headers)
        elif auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {os.environ['AGENT_BEARER_TOKEN']}"
        else:
            fail(f"unknown --agent-auth {auth_mode}")
        t0 = time.perf_counter()
        r = httpx.post(url, content=body, headers=headers, timeout=300)
        s = time.perf_counter() - t0
        if r.status_code != 200:
            print(f"  {p['id']:8s} HTTP {r.status_code} {r.text[:200]}")
            bad += 1
            continue
        c = (r.json().get("classification") or {}).get("hts10", "")
        good = bool(HTS10.match(c))
        bad += 0 if good else 1
        print(f"  {p['id']:8s} {c or '(none)'} chapter match {c[:2] == p['chapter']} ({s:.1f} s)")
    return bad


def vertex_part(resource: str) -> int:
    try:
        import vertexai
    except ImportError:
        fail("the vertexai SDK is missing; run with deploy/gcp/.venv/bin/python")
    m = re.match(r"projects/([^/]+)/locations/([^/]+)/reasoningEngines/[^/]+$", resource)
    if not m:
        fail("--vertex-agent must be projects/P/locations/L/reasoningEngines/ID")
    client = vertexai.Client(project=m.group(1), location=m.group(2))
    app = client.agent_engines.get(name=resource)
    bad = 0
    for p in PRODUCTS:
        text = ""
        for ev in app.stream_query(user_id=f"smoke-{p['id']}", message=p["description"]):
            for part in (ev.get("content") or {}).get("parts", []):
                text += part.get("text", "")
        mm = re.search(r"\d{4}\.\d{2}\.\d{2}\.\d{2}", text)
        bad += 0 if mm else 1
        print(f"  {p['id']:8s} {mm.group(0) if mm else '(none)'}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mcp-url")
    ap.add_argument("--mcp-auth", default="none", choices=["none", "bearer", "sigv4", "google-id-token"])
    ap.add_argument("--tool-prefix", default="", help="AgentCore Gateway prefix, '<target>___'")
    ap.add_argument("--agent-url", help="AgentCore InvokeAgentRuntime HTTPS URL")
    ap.add_argument("--agent-auth", default="sigv4", choices=["sigv4", "bearer"])
    ap.add_argument("--vertex-agent", help="Agent Runtime resource name")
    ap.add_argument("--strict", action="store_true", help="fail when an expected chapter is missing")
    a = ap.parse_args(argv)
    if not (a.mcp_url or a.agent_url or a.vertex_agent):
        ap.error("give --mcp-url, --agent-url or --vertex-agent")

    failures = 0
    if a.mcp_url:
        guard(a.mcp_url)
        misses = asyncio.run(mcp_part(a.mcp_url, a.mcp_auth, a.tool_prefix))
        failures += misses if a.strict else 0
    if a.agent_url:
        guard(a.agent_url)
        failures += agentcore_part(a.agent_url, a.agent_auth)
    if a.vertex_agent:
        guard("aiplatform.googleapis.com")
        failures += vertex_part(a.vertex_agent)
    if failures:
        fail(f"{failures} product checks failed")
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
