"""A scripted stand-in for Claude on Bedrock, for local validation only.

It plugs into the real BedrockProvider (tariffagent.llm.cloud) through a mocked
httpx2 transport, so the request that would go to Bedrock is built, signed with
fake keys and inspected, but nothing leaves the process. The replies follow a
fixed tool plan (hts_search, then hts_navigate plus cross_search, then
ruling_status, then a final Classification JSON) and read codes and ruling ids
out of the real tool results the agent got from the MCP server.

The answers are not model output. They exist to prove the wiring: agent loop,
MCP client over HTTP, Bedrock request shape. Never enable this in a deployment.
"""

from __future__ import annotations

import json
import re
import threading

import httpx2

HTS10 = re.compile(r"\b(\d{4}\.\d{2}\.\d{2}\.\d{2})\b")
RULING_ID = re.compile(r'"id":"([A-Z]{1,2}\d{5,6})"')
STATUS = re.compile(r'"status":"(in_force|modified|revoked|unknown)"')


def _text_of(block: dict) -> str:
    c = block.get("content", "")
    if isinstance(c, str):
        return c
    return "".join(x.get("text", "") for x in c if isinstance(x, dict))


def _tool_results(messages: list[dict]) -> dict[str, str]:
    """Map tool name -> latest result text, using the tool_use ids from assistant turns."""
    names: dict[str, str] = {}
    out: dict[str, str] = {}
    for m in messages:
        if not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if b.get("type") == "tool_use":
                names[b["id"]] = b["name"]
            elif b.get("type") == "tool_result":
                out[names.get(b["tool_use_id"], "?")] = _text_of(b)
    return out


def _description(messages: list[dict]) -> str:
    first = messages[0]["content"]
    text = first if isinstance(first, str) else "".join(b.get("text", "") for b in first)
    m = re.search(r"<product_description>\s*(.*?)\s*</product_description>", text, re.S)
    return (m.group(1) if m else text)[:200]


def _tool_use(i: int, name: str, args: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_scripted_{i}_{name}", "name": name, "input": args}


class ScriptedClaude:
    """httpx2.MockTransport handler that answers Anthropic Messages requests."""

    def __init__(self):
        self.requests: list[dict] = []
        self.urls: list[str] = []
        self._lock = threading.Lock()

    def reply(self, body: dict) -> dict:
        msgs = body["messages"]
        results = _tool_results(msgs)
        desc = _description(msgs)
        turn = sum(1 for m in msgs if m["role"] == "assistant") + 1
        if "hts_search" not in results:
            content = [_tool_use(turn, "hts_search", {"text": desc[:120], "limit": 8})]
            stop = "tool_use"
        elif "cross_search" not in results:
            codes = HTS10.findall(results["hts_search"])
            content = [_tool_use(turn, "cross_search", {"query": desc[:120], "limit": 5})]
            if codes:
                content.append(_tool_use(turn, "hts_navigate", {"code": codes[0]}))
            stop = "tool_use"
        elif "ruling_status" not in results and RULING_ID.search(results["cross_search"]):
            rid = RULING_ID.search(results["cross_search"]).group(1)
            content = [_tool_use(turn, "ruling_status", {"id": rid})]
            stop = "tool_use"
        else:
            codes = HTS10.findall(results.get("hts_navigate", "")) or HTS10.findall(results["hts_search"])
            cited = []
            if "ruling_status" in results:
                rid = RULING_ID.search(results["ruling_status"]) or RULING_ID.search(results["cross_search"])
                st = STATUS.search(results["ruling_status"])
                if rid:
                    cited = [{"id": rid.group(1), "status": st.group(1) if st else "unknown"}]
            answer = {
                "hts10": codes[0] if codes else "",
                "facts": {"material": "", "function": "", "form": "", "end_use": ""},
                "gri_path": ["GRI 1: scripted local validation answer, not model output"],
                "deciding_gri": "GRI 1",
                "cited_rulings": cited,
                "rejected_alternatives": [],
                "missing_facts": [],
                "confidence": 0.0,
                "abstain": not codes,
                "rationale": "Scripted reply used to validate the deploy package wiring. Not a classification.",
            }
            content = [{"type": "text", "text": json.dumps(answer)}]
            stop = "end_turn"
        return {
            "id": f"msg_scripted_{turn}",
            "type": "message",
            "role": "assistant",
            "model": body["model"],
            "content": content,
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        }

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        with self._lock:
            self.requests.append(body)
            self.urls.append(str(request.url))
        return httpx2.Response(200, json=self.reply(body))

    def summary(self) -> dict:
        """Facts about the Bedrock requests the agent built, for the validation checks."""
        return {
            "requests": len(self.requests),
            "model_ids": sorted({r["model"] for r in self.requests}),
            "hosts": sorted({re.sub(r"^https?://([^/]+).*$", r"\1", u) for u in self.urls}),
            "system_cache_breakpoint": all(
                isinstance(r.get("system"), list) and r["system"][-1].get("cache_control") is not None
                for r in self.requests
            ),
            "structured_output": all(
                r.get("output_config", {}).get("format", {}).get("type") == "json_schema"
                for r in self.requests
            ),
            "tools_sent": sorted({t["name"] for r in self.requests for t in r.get("tools", [])}),
        }


def scripted_bedrock_provider(region: str = "us-east-1"):
    """A real BedrockProvider whose HTTP client never leaves the process."""
    from anthropic import AnthropicBedrockMantle

    from tariffagent.llm.cloud import BedrockProvider

    handler = ScriptedClaude()
    client = AnthropicBedrockMantle(
        aws_region=region,
        aws_access_key="AKIASCRIPTEDLOCAL000",
        aws_secret_key="scripted-local-validation-only",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return BedrockProvider(client), handler
