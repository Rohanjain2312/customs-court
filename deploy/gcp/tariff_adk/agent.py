"""TariffAgent orchestrator as a Google ADK agent for Vertex AI Agent Runtime.

Deploy-ready, not deployed. Checked against google-adk 2.10.0 and
google-cloud-aiplatform 2.2.0 (installed in deploy/gcp/.venv) on 2026-09-28.

The team mirrors the project's multi-agent design (src/tariffagent/agents/multi.py):

    tariffagent (SequentialAgent)
      orchestrator   cheap model; hts_search, hts_navigate; writes state["plan"]
      advocates      ParallelAgent of up to 3 read-only advocates, one heading each;
                     get_notes, cross_search, get_ruling, ruling_status, ...; state["memo_i"]
      adjudicator    strong model, the only writer; hts_navigate, ruling_status;
                     state["classification"] (the final JSON)

Tools come from the TariffAgent MCP server on Cloud Run through ADK's McpToolset over
streamable HTTP, authenticated with a Google ID token (tariff_adk.auth).
Models default to ADK's own Claude class, which serves Claude from Vertex AI with
prompt-cache breakpoints when the App has a context cache config.
Prompts come from _assets.json, generated from the tariffagent package by
deploy/gcp/build_assets.py, so the text matches the eval harness.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

ASSETS = Path(__file__).resolve().parent / "_assets.json"
MAX_ADVOCATES = 3
DEFAULT_MCP_URL = "http://127.0.0.1:8080/mcp"


@lru_cache
def assets() -> dict:
    if not ASSETS.exists():
        raise RuntimeError(f"{ASSETS} is missing. Run deploy/gcp/build_assets.py first.")
    return json.loads(ASSETS.read_text())


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _state_text(state, key: str) -> str:
    v = state.get(key, "")
    return v if isinstance(v, str) else json.dumps(v)


def candidate_headings(state) -> list[str]:
    plan = parse_json(_state_text(state, "plan"))
    heads = []
    for h in plan.get("candidate_headings") or []:
        d = re.sub(r"\D", "", str(h))[:4]
        if len(d) == 4 and d not in heads:
            heads.append(d)
    return heads[:MAX_ADVOCATES]


def _product_block(state) -> str:
    return f"<product_description>\n{state.get('product', '')}\n</product_description>"


# ---- Callbacks and instruction providers (callables bypass ADK state templating) ----


def remember_product(callback_context):
    """Root callback: keep the user's product text in state for sub-agents without history."""
    content = callback_context.user_content
    text = "".join(p.text or "" for p in (content.parts or [])) if content else ""
    callback_context.state["product"] = text.strip()[:4000]
    return None


def orchestrator_instruction(ctx) -> str:
    return assets()["orchestrator_role"] + "\n\n" + _product_block(ctx.state)


def make_advocate_instruction(i: int):
    def instruction(ctx) -> str:
        heads = candidate_headings(ctx.state)
        heading = heads[i] if i < len(heads) else ""
        plan = parse_json(_state_text(ctx.state, "plan"))
        return (
            # Plain replace, not str.format: the role text contains JSON braces and, in
            # newer versions of multi.py, names the heading in the message instead.
            assets()["advocate_role"].replace("{heading}", heading)
            + f"\n\nHeading under review: {heading}\n"
            + _product_block(ctx.state)
            + f"\n\n<facts>{json.dumps(plan.get('facts', {}))}</facts>"
        )

    instruction.__name__ = f"advocate_{i + 1}_instruction"
    return instruction


def make_advocate_skip(i: int):
    """Skip an advocate slot when the orchestrator proposed fewer headings."""

    def skip(callback_context):
        if i < len(candidate_headings(callback_context.state)):
            return None
        return types.Content(role="model", parts=[types.Part(text='{"skipped": true}')])

    skip.__name__ = f"advocate_{i + 1}_skip"
    return skip


def adjudicator_instruction(ctx) -> str:
    plan = parse_json(_state_text(ctx.state, "plan"))
    memos = []
    for i in range(MAX_ADVOCATES):
        m = parse_json(_state_text(ctx.state, f"memo_{i + 1}"))
        if m and not m.get("skipped"):
            memos.append(m)
    return (
        assets()["adjudicator_role"]
        + "\n\n"
        + _product_block(ctx.state)
        + f"\n\n<facts>{json.dumps(plan.get('facts', {}))}</facts>"
        + f"\n<missing_facts>{json.dumps(plan.get('missing_facts', []))}</missing_facts>"
        + f"\n<advocate_memos>{json.dumps(memos)}</advocate_memos>"
    )


# ---- Models -------------------------------------------------------------------------


def vertex_claude(role: str):
    """ADK's Claude-on-Vertex model for 'advocate' (cheap) or 'reasoner' (strong).

    The full resource path carries project and region, so the deployed agent does not
    depend on GOOGLE_CLOUD_* variables. No request is made until the agent runs.
    """
    from google.adk.models.anthropic_llm import Claude

    a = assets()
    name = os.environ.get("REASONER_MODEL" if role == "reasoner" else "ADVOCATE_MODEL") or a["models"][role]
    vid = a["vertex_model_ids"].get(name, name)
    project = os.environ["GOOGLE_CLOUD_PROJECT_ID"]
    region = os.environ.get("CLAUDE_VERTEX_REGION", "global")
    return Claude(
        model=f"projects/{project}/locations/{region}/publishers/anthropic/models/{vid}", max_tokens=2000
    )


def default_models() -> dict:
    return {
        "orchestrator": vertex_claude("advocate"),
        "advocate": vertex_claude("advocate"),
        "adjudicator": vertex_claude("reasoner"),
    }


# ---- Agent tree ---------------------------------------------------------------------


def toolset(names: list[str], mcp_url: str, header_provider) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=mcp_url, timeout=60),
        tool_filter=sorted(names),
        header_provider=header_provider,
    )


def build_root_agent(models: dict | None = None, mcp_url: str | None = None, header_provider=None):
    """Build the agent tree. models maps orchestrator/advocate/adjudicator to ADK models."""
    a = assets()
    mcp_url = mcp_url or os.environ.get("MCP_URL", DEFAULT_MCP_URL)
    if header_provider is None and os.environ.get("MCP_AUTH", "google-id-token") == "google-id-token":
        from tariff_adk.auth import IdTokenHeaders, audience_for

        header_provider = IdTokenHeaders(audience_for(mcp_url))
    models = models or default_models()
    # Skill body and GRI text: the same static, cacheable block for every agent.
    static = a["skill_block"] + "\n\n" + a["gri_block"]

    orchestrator = LlmAgent(
        name="orchestrator",
        description="Extracts facts and proposes 2 to 4 candidate headings.",
        model=models["orchestrator"],
        static_instruction=static,
        instruction=orchestrator_instruction,
        tools=[toolset(a["orchestrator_tools"], mcp_url, header_provider)],
        output_key="plan",
        include_contents="none",
    )
    advocates = [
        LlmAgent(
            name=f"advocate_{i + 1}",
            description="Argues for one candidate heading. Read-only.",
            model=models["advocate"],
            static_instruction=static,
            instruction=make_advocate_instruction(i),
            tools=[toolset(a["advocate_tools"], mcp_url, header_provider)],
            output_key=f"memo_{i + 1}",
            include_contents="none",
            before_agent_callback=make_advocate_skip(i),
        )
        for i in range(MAX_ADVOCATES)
    ]
    adjudicator = LlmAgent(
        name="adjudicator",
        description="Applies the GRIs, weighs the memos and writes the final classification.",
        model=models["adjudicator"],
        static_instruction=static,
        instruction=adjudicator_instruction,
        tools=[toolset(a["adjudicator_tools"], mcp_url, header_provider)],
        output_key="classification",
        include_contents="none",
    )
    return SequentialAgent(
        name="tariffagent",
        description="TariffAgent: US HTS classification grounded in CBP CROSS rulings.",
        sub_agents=[
            orchestrator,
            ParallelAgent(name="advocates", sub_agents=advocates),
            adjudicator,
        ],
        before_agent_callback=remember_product,
    )


def build_app(root_agent=None):
    """ADK App with context caching on, so the Claude model marks cache breakpoints."""
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps.app import App

    return App(
        name="tariffagent",
        root_agent=root_agent or build_root_agent(),
        context_cache_config=ContextCacheConfig(ttl_seconds=300, cache_intervals=10, min_tokens=1024),
    )
