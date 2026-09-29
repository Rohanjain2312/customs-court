"""Run the ADK agent locally against a local MCP server with scripted models.

    deploy/gcp/.venv/bin/python deploy/gcp/local_validation/run_local_adk.py http://127.0.0.1:18800/mcp

No model API and no Google Cloud call: the models are ScriptedLlm (scripted_llm.py) and
the MCP server is the local Cloud Run image. Checks:
- every role ran and called its MCP tools, and the tools returned data;
- state hand-off: plan -> advocate memos -> classification;
- the final classification has every field of the Classification schema;
- the same tree wraps in vertexai.agent_engines.AdkApp (the object Agent Runtime deploys).
Exits non-zero on the first failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # tariff_adk
sys.path.insert(0, str(HERE))  # scripted_llm

PRODUCT = (
    "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, "
    "two shoulder straps and a polyester lining."
)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


async def run(mcp_url: str) -> None:
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from scripted_llm import ScriptedLlm, scripted_models
    from tariff_adk.agent import assets, build_app, build_root_agent

    os.environ["MCP_AUTH"] = "none"
    root = build_root_agent(models=scripted_models(), mcp_url=mcp_url)
    app = build_app(root)
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name=app.name, user_id="local")
    msg = types.Content(role="user", parts=[types.Part(text=PRODUCT)])

    calls: list[tuple[str, str]] = []
    responses: list[tuple[str, str, str]] = []
    async for ev in runner.run_async(user_id="local", session_id=session.id, new_message=msg):
        for p in (ev.content.parts if ev.content else None) or []:
            if p.function_call:
                calls.append((ev.author, p.function_call.name))
            if p.function_response:
                responses.append(
                    (ev.author, p.function_response.name, json.dumps(p.function_response.response))
                )
    state = (
        await runner.session_service.get_session(app_name=app.name, user_id="local", session_id=session.id)
    ).state

    authors = {a for a, _ in calls}
    for role in ("orchestrator", "advocate_1", "adjudicator"):
        if role not in authors:
            fail(f"{role} made no tool call; calls: {calls}")
    print(f"  ok  tool calls by agent: {sorted(set(calls))}")
    errors = [r for r in responses if '"isError": true' in r[2] or '"is_error": true' in r[2]]
    if errors:
        fail(f"MCP tool errors: {errors[:2]}")
    hs = [r for r in responses if r[1] == "hts_search"]
    if not hs or '"hits"' not in hs[0][2]:
        fail("hts_search over MCP returned no hits")
    print(f"  ok  {len(responses)} MCP tool results, none an error")

    plan = json.loads(re.search(r"\{.*\}", state["plan"], re.S).group(0))
    if not plan.get("candidate_headings"):
        fail(f"orchestrator plan has no candidate headings: {plan}")
    memos = [k for k in state if k.startswith("memo_")]
    print(f"  ok  plan headings {plan['candidate_headings']}, memos in state: {sorted(memos)}")

    final = json.loads(re.search(r"\{.*\}", state["classification"], re.S).group(0))
    required = assets()["classification_schema"]["required"]
    missing = [k for k in required if k not in final]
    if missing:
        fail(f"classification misses fields {missing}")
    if not final["abstain"] and not re.match(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$", final["hts10"]):
        fail(f"hts10 is not a 10-digit code: {final['hts10']!r}")
    print(
        f"  ok  classification {final['hts10']} cites {final['cited_rulings']} (scripted, not model output)"
    )
    roles = sorted({c["role"] for c in ScriptedLlm.calls})
    print(f"  ok  scripted model calls: {len(ScriptedLlm.calls)} across roles {roles}")

    try:
        import vertexai
        from vertexai.agent_engines import AdkApp
    except ImportError as e:
        fail(f"vertexai AdkApp not importable: {e}")
    # A placeholder project id: AdkApp reads it at construction. Nothing is sent anywhere.
    vertexai.init(project="local-validation-no-calls", location="us-central1")
    AdkApp(app=app)
    print("  ok  AdkApp(app=...) wraps the agent tree (constructed only, not deployed)")


def main() -> None:
    url = sys.argv[1]
    if urlparse(url).hostname not in {"127.0.0.1", "localhost"}:
        fail("run_local_adk.py only runs against a local MCP server")
    asyncio.run(run(url))
    print("ADK local run passed (scripted models, local MCP server)")


if __name__ == "__main__":
    main()
