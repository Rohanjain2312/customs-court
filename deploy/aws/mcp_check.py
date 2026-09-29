"""Call every TariffAgent MCP tool on a running server. Deploy-ready, not deployed.

Used by deploy/aws/build_and_validate.sh and deploy/gcp/build_and_validate.sh
against a local container only.

    uv run python deploy/aws/mcp_check.py http://127.0.0.1:18000/mcp [--fixture] [--redacted]
        [--allowed-host HOST] [--bearer TOKEN]

Checks:
- tools/list returns exactly the 8 tools;
- each tool is called with real arguments and returns structured content;
- a raw JSON-RPC POST that carries a platform-made Mcp-Session-Id is accepted
  (AgentCore adds that header in stateless mode; the server must not reject it);
- with --fixture --redacted, an evaluation ruling is hidden;
- with --allowed-host, a request with a foreign Host header is rejected.
Exits non-zero on the first failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from urllib.parse import urlparse

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

EXPECTED = {
    "hts_navigate",
    "hts_search",
    "get_notes",
    "get_gri",
    "cross_search",
    "get_ruling",
    "ruling_status",
    "hts_revision_diff",
}
FIXTURE_GOLDEN = "N326421"  # listed in tests/fixtures/data/fixture_info.json; redacted with --redact-eval


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def _server(url: str, bearer: str | None):
    if not bearer:
        return url
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {bearer}"}, timeout=60)
    return streamable_http_client(url, http_client=http)


async def call(client: Client, name: str, args: dict) -> dict:
    res = await client.call_tool(name, args)
    if res.is_error:
        fail(f"{name} returned an error: {[getattr(c, 'text', '') for c in res.content]}")
    data = res.structured_content
    if not isinstance(data, dict):
        fail(f"{name} returned no structured content")
    preview = json.dumps(data, ensure_ascii=False)[:110]
    print(f"  ok  {name:18s} {json.dumps(args)[:60]:60s} -> {preview}", flush=True)
    return data


async def exercise(url: str, fixture: bool, redacted: bool, bearer: str | None) -> None:
    async with Client(_server(url, bearer)) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        if tools != EXPECTED:
            fail(f"tool list mismatch: {sorted(tools)}")
        print(f"  ok  list_tools         {len(tools)} tools: {', '.join(sorted(tools))}", flush=True)

        nav = await call(client, "hts_navigate", {"code": "4202.21"})
        if not nav.get("found"):
            fail("hts_navigate did not find 4202.21")
        srch = await call(client, "hts_search", {"text": "leather handbag", "limit": 5})
        if not srch.get("hits"):
            fail("hts_search returned no hits")
        notes = await call(client, "get_notes", {"scope": "chapter", "id": "42"})
        if not notes.get("found"):
            fail("get_notes chapter 42 not found")
        gri = await call(client, "get_gri", {})
        if "summary" not in gri:
            fail("get_gri has no summary")
        cs = await call(client, "cross_search", {"query": "leather handbag shoulder strap", "limit": 5})
        hits = cs.get("hits") or []
        if not hits:
            fail("cross_search returned no hits")
        rid = hits[0]["id"]
        rul = await call(client, "get_ruling", {"id": rid})
        if not rul.get("found") or rul["text"]["kind"] != "untrusted_corpus_text":
            fail(f"get_ruling {rid} missing or not wrapped as untrusted_corpus_text")
        st = await call(client, "ruling_status", {"id": rid})
        if st.get("status") not in {"in_force", "modified", "revoked", "unknown"}:
            fail(f"ruling_status gave {st.get('status')}")
        diff = await call(client, "hts_revision_diff", {"code": "4202.21.90.00", "rev_a": "2018"})
        if "change" not in diff:
            fail("hts_revision_diff has no change field")
        if fixture and redacted:
            g = await client.call_tool("get_ruling", {"id": FIXTURE_GOLDEN})
            if g.structured_content.get("found") is not False:
                fail(f"eval ruling {FIXTURE_GOLDEN} is visible although the server runs --redact-eval")
            print(f"  ok  redaction          {FIXTURE_GOLDEN} hidden", flush=True)


def raw_post(url: str, host: str | None = None, session_id: str | None = None, bearer: str | None = None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-06-18",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if host:
        headers["Host"] = host
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    return httpx.post(url, json=body, headers=headers, timeout=30)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--fixture", action="store_true", help="server runs on the test fixture data")
    ap.add_argument("--redacted", action="store_true", help="server runs with --redact-eval")
    ap.add_argument("--allowed-host", default=None, help="Host value the server allows (MCP_ALLOWED_HOSTS)")
    ap.add_argument("--bearer", default=None)
    a = ap.parse_args()

    host = urlparse(a.url).hostname or ""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        fail("mcp_check.py only runs against a local container")

    print(f"MCP client -> {a.url}", flush=True)
    asyncio.run(exercise(a.url, a.fixture, a.redacted, a.bearer))

    sid = "platform-" + uuid.uuid4().hex
    r = raw_post(a.url, host=a.allowed_host, session_id=sid, bearer=a.bearer)
    if r.status_code != 200:
        fail(f"POST with a platform Mcp-Session-Id was rejected: {r.status_code} {r.text[:200]}")
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    n = len(body.get("result", {}).get("tools", []))
    if n != len(EXPECTED):
        fail(f"raw tools/list with Mcp-Session-Id returned {n} tools: {r.text[:200]}")
    print(f"  ok  stateless          POST with Mcp-Session-Id={sid[:18]}... accepted, {n} tools", flush=True)

    if a.allowed_host:
        bad = raw_post(a.url, host="attacker.example", bearer=a.bearer)
        if bad.status_code < 400:
            fail(f"foreign Host header was accepted ({bad.status_code})")
        print(f"  ok  host check         foreign Host rejected with {bad.status_code}", flush=True)
    print("MCP container check passed", flush=True)


if __name__ == "__main__":
    main()
