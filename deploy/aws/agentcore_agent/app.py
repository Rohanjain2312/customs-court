"""TariffAgent agent entrypoint for Amazon Bedrock AgentCore Runtime (HTTP protocol).

Deploy-ready, not deployed.

AgentCore HTTP contract (docs checked 2026-09-28, runtime-http-protocol-contract.html):
host 0.0.0.0, port 8080, POST /invocations (JSON in, JSON out), GET /ping returning
{"status": "Healthy"}, ARM64 image.

The agent is the project's single agent (arm A): the same episode code as the eval
harness (tariffagent.agents.single), with the model called through BedrockProvider
and the tools called through a real MCP client over streamable HTTP.

Environment:
  MCP_URL           MCP endpoint. In AWS: the AgentCore Gateway URL. Locally: the MCP container.
  MCP_AUTH          sigv4 (default, signs for service bedrock-agentcore), bearer or none.
  MCP_BEARER_TOKEN  token for MCP_AUTH=bearer.
  MCP_TOOL_PREFIX   prefix the gateway puts on tool names, "<target name>___". Empty locally.
  AWS_REGION        region for Bedrock and SigV4.
  AGENT_MODEL_MODE  bedrock (default) or scripted. scripted is for local validation only:
                    BedrockProvider runs against an in-process mock and never calls AWS.
  REASONER_MODEL    model name, default claude-sonnet-5 (mapped to anthropic.claude-sonnet-5).
  AGENT_MAX_TURNS, AGENT_TOKEN_BUDGET  hard caps per invocation.
  I_ACCEPT_CLOUD_COSTS=yes is required to build a real Bedrock client (tariffagent.llm.cloud).

Payload: {"description": "..."} (or {"prompt": "..."}), optional "item_id".
"""

from __future__ import annotations

import os
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

MAX_DESCRIPTION_CHARS = 4000

app = FastAPI(title="tariffagent-agentcore", version="0.1.0")

_provider = None
_scripted = None
_lock = threading.Lock()


def model_mode() -> str:
    mode = os.environ.get("AGENT_MODEL_MODE", "bedrock").strip().lower()
    if mode not in {"bedrock", "scripted"}:
        raise RuntimeError(f"AGENT_MODEL_MODE must be bedrock or scripted, not {mode!r}")
    return mode


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def get_provider():
    """One provider per process. The real one refuses without I_ACCEPT_CLOUD_COSTS=yes."""
    global _provider, _scripted
    with _lock:
        if _provider is None:
            if model_mode() == "scripted":
                from agentcore_agent.scripted_bedrock import scripted_bedrock_provider

                _provider, _scripted = scripted_bedrock_provider(region())
            else:
                from tariffagent.llm.cloud import BedrockProvider

                _provider = BedrockProvider.from_env(region())
        return _provider


def mcp_transport():
    """Streamable HTTP transport for the MCP client, with the configured auth."""
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    url = os.environ.get("MCP_URL", "").strip()
    if not url:
        raise RuntimeError("MCP_URL is not set")
    mode = os.environ.get("MCP_AUTH", "sigv4").strip().lower()
    headers = {"User-Agent": "tariffagent-agentcore/0.1"}
    auth = None
    if mode == "sigv4":
        from agentcore_agent.sigv4 import SigV4Auth

        auth = SigV4Auth(region())
    elif mode == "bearer":
        headers["Authorization"] = f"Bearer {os.environ['MCP_BEARER_TOKEN']}"
    elif mode != "none":
        raise RuntimeError(f"MCP_AUTH must be sigv4, bearer or none, not {mode!r}")
    http = httpx2.AsyncClient(headers=headers, auth=auth, timeout=httpx2.Timeout(60.0, read=120.0))
    return streamable_http_client(url, http_client=http)


class PrefixedBackend:
    """AgentCore Gateway lists target tools as '<target>___<tool>'. The agent uses bare names."""

    def __init__(self, inner, prefix: str):
        self.inner = inner
        self.prefix = prefix

    def call(self, name: str, args: dict) -> str:
        return self.inner.call(f"{self.prefix}{name}", args)

    def close(self) -> None:
        self.inner.close()


def classify(description: str, item_id: str | None = None) -> dict:
    from tariffagent.agents.events import EventBus
    from tariffagent.agents.runner import drive
    from tariffagent.agents.single import AgentConfig, single_episode
    from tariffagent.agents.tooling import MCPBackend, ToolExecutor

    provider = get_provider()
    run_id = f"agentcore-{uuid.uuid4().hex[:12]}"
    item = {"item_id": item_id or run_id, "description": description}
    cfg = AgentConfig.for_arm(
        "A",
        run_id=run_id,
        max_turns=int(os.environ.get("AGENT_MAX_TURNS", "10")),
        token_budget=int(os.environ.get("AGENT_TOKEN_BUDGET", "120000")),
    )
    bus = EventBus(run_id)
    backend = MCPBackend(mcp_transport())
    prefix = os.environ.get("MCP_TOOL_PREFIX", "")
    tools = PrefixedBackend(backend, prefix) if prefix else backend
    t0 = time.perf_counter()
    try:
        res = drive(single_episode(item, cfg, ToolExecutor(tools, bus), bus), complete=provider.complete)
    finally:
        backend.close()
    out = {
        "item_id": res.get("item_id"),
        "classification": res.get("classification"),
        "parse_error": res.get("parse_error", ""),
        "turns": res.get("turns"),
        "tool_calls": res.get("tool_calls"),
        "usage": res.get("usage"),
        "tokens": res.get("tokens"),
        "wall_s": round(time.perf_counter() - t0, 3),
        "model_mode": model_mode(),
        "model": cfg.model,
        "tools_used": sorted({e.tool for e in bus.events if getattr(e, "type", "") == "tool_call"}),
    }
    if _scripted is not None:
        out["scripted_bedrock_requests"] = _scripted.summary()
    return out


@app.get("/ping")
async def ping() -> dict:
    # No time_of_last_update: the contract says to set it only on a real status change.
    return {"status": "Healthy"}


@app.post("/invocations")
async def invocations(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="body must be JSON") from e
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    desc = body.get("description") or body.get("prompt") or ""
    if not isinstance(desc, str) or not desc.strip():
        raise HTTPException(status_code=400, detail="'description' must be a non-empty string")
    if len(desc) > MAX_DESCRIPTION_CHARS:
        raise HTTPException(status_code=400, detail=f"'description' is longer than {MAX_DESCRIPTION_CHARS}")
    item_id = body.get("item_id") if isinstance(body.get("item_id"), str) else None
    try:
        return await run_in_threadpool(classify, desc.strip(), item_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        # Log the detail server side; return a short message (no stack traces to callers).
        import logging

        logging.getLogger("tariffagent.agentcore").exception("classification failed")
        raise HTTPException(status_code=500, detail=f"classification failed: {type(e).__name__}") from e
