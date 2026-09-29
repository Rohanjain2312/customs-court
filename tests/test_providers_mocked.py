"""Provider adapters tested with mocked HTTP transports and recorded-shape responses.

Bedrock and Vertex are never called live (they bill outside the allowed vendors).
"""

import json

import httpx
import httpx2
import pytest

from tariffagent.llm.base import LLMRequest, ToolSpec

ANTHROPIC_MSG = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5",
    "content": [
        {"type": "text", "text": "Checking the heading."},
        {"type": "tool_use", "id": "toolu_1", "name": "hts_navigate", "input": {"code": "4202"}},
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 12,
        "output_tokens": 30,
        "cache_creation_input_tokens": 4000,
        "cache_read_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 4000, "ephemeral_1h_input_tokens": 0},
    },
}


def _req(**kw) -> LLMRequest:
    return LLMRequest(
        model="claude-sonnet-5",
        system=[{"type": "text", "text": "static prefix"}],
        messages=[{"role": "user", "content": "classify a leather handbag"}],
        tools=[
            ToolSpec(
                "hts_navigate",
                "nav",
                {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            )
        ],
        max_tokens=500,
        output_schema={
            "type": "object",
            "properties": {"hts10": {"type": "string"}},
            "required": ["hts10"],
            "additionalProperties": False,
        },
        **{"effort": "low", **kw},
    )


class Capture:
    """Mock transport handler. Works for both httpx and httpx2 request objects."""

    def __init__(self, body: dict):
        self.body = body
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        mod = httpx2 if type(request).__module__.startswith("httpx2") else httpx
        return mod.Response(200, json=self.body)


def test_build_params_places_two_cache_breakpoints_and_structured_output():
    from tariffagent.llm.anthropic_provider import build_params

    p = build_params(_req())
    assert p["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert p["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert p["output_config"]["format"]["type"] == "json_schema"
    assert p["output_config"]["effort"] == "low"
    assert "temperature" not in p


def test_haiku_temperature_goes_through_extra_body():
    from tariffagent.llm.anthropic_provider import build_params

    r = _req(temperature=0.0)
    r.model = "claude-haiku-4-5"
    assert build_params(r)["extra_body"] == {"temperature": 0.0}
    assert build_params(r, for_batch=True)["temperature"] == 0.0


def test_bedrock_adapter_with_mocked_transport():
    from anthropic import AnthropicBedrockMantle

    from tariffagent.llm.cloud import BedrockProvider

    cap = Capture(ANTHROPIC_MSG)
    client = AnthropicBedrockMantle(
        aws_region="us-east-1",
        aws_access_key="AKIATEST",
        aws_secret_key="secret",
        http_client=httpx2.Client(transport=httpx2.MockTransport(cap)),
    )
    resp = BedrockProvider(client).complete(_req())
    sent = json.loads(cap.requests[0].content)
    assert sent["model"] == "anthropic.claude-sonnet-5"
    assert sent["system"][-1]["cache_control"]["type"] == "ephemeral"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "bedrock" in str(cap.requests[0].url)
    assert resp.tool_uses[0]["name"] == "hts_navigate"
    assert resp.usage.cache_write_5m_tokens == 4000


def test_vertex_claude_adapter_with_mocked_transport():
    from anthropic import AnthropicVertex

    from tariffagent.llm.cloud import VertexClaudeProvider

    cap = Capture(ANTHROPIC_MSG)
    client = AnthropicVertex(
        project_id="test-project",
        region="global",
        access_token="token",
        http_client=httpx2.Client(transport=httpx2.MockTransport(cap)),
    )
    r = _req()
    r.model = "claude-haiku-4-5"
    resp = VertexClaudeProvider(client).complete(r)
    url = str(cap.requests[0].url)
    assert "aiplatform.googleapis.com" in url and "claude-haiku-4-5@20251001" in url
    assert resp.stop_reason == "tool_use"


def test_vertex_gemini_adapter_translates_tools_and_usage():
    from tariffagent.llm.cloud import VertexGeminiProvider

    body = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"functionCall": {"name": "hts_navigate", "args": {"code": "4202"}}}],
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 900,
            "candidatesTokenCount": 20,
            "cachedContentTokenCount": 600,
        },
    }
    cap = Capture(body)
    prov = VertexGeminiProvider(httpx.Client(transport=httpx.MockTransport(cap)), project="p", token="t")
    r = _req()
    r.messages = r.messages + [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "a", "name": "hts_search", "input": {"text": "bag"}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "a", "name": "hts_search", "content": "{}"}],
        },
    ]
    resp = prov.complete(r)
    sent = json.loads(cap.requests[0].content)
    assert sent["tools"][0]["functionDeclarations"][0]["name"] == "hts_navigate"
    assert sent["systemInstruction"]["parts"][0]["text"] == "static prefix"
    assert [c["role"] for c in sent["contents"]] == ["user", "model", "user"]
    assert resp.tool_uses[0]["input"] == {"code": "4202"}
    assert resp.usage.cache_read_tokens == 600 and resp.usage.input_tokens == 300


def test_cloud_clients_refuse_without_opt_in(monkeypatch):
    from tariffagent.llm.cloud import BedrockProvider, CloudCostGuard, VertexClaudeProvider

    monkeypatch.delenv("I_ACCEPT_CLOUD_COSTS", raising=False)
    with pytest.raises(CloudCostGuard):
        BedrockProvider.from_env()
    with pytest.raises(CloudCostGuard):
        VertexClaudeProvider.from_env(project_id="x")


def test_openai_adapter_with_mocked_transport(monkeypatch, tmp_path):
    import openai

    from tariffagent import config
    from tariffagent.llm.openai_provider import OpenAIProvider

    monkeypatch.setenv("OFFLINE", "false")
    monkeypatch.setenv("CACHE_DIR_OVERRIDE", str(tmp_path))
    monkeypatch.setenv("LEDGER_FILE", str(tmp_path / "ledger.jsonl"))
    config.get_settings.cache_clear()
    body = {
        "id": "c1",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-5-mini",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "hts_navigate", "arguments": '{"code": "4202"}'},
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 40,
            "total_tokens": 1040,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
    }
    cap = Capture(body)
    client = openai.OpenAI(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(cap)))
    r = _req()
    r.model = "gpt-5-mini"
    resp = OpenAIProvider(client).complete(r)
    sent = json.loads(cap.requests[0].content)
    assert sent["messages"][0]["role"] == "system"
    assert sent["response_format"]["type"] == "json_schema"
    assert resp.stop_reason == "tool_use" and resp.tool_uses[0]["input"] == {"code": "4202"}
    assert resp.usage.cache_read_tokens == 800 and resp.usage.input_tokens == 200
    assert resp.usd > 0


def test_prewarm_writes_prefix_once_per_shared_prefix():
    from tariffagent.llm.anthropic_provider import AnthropicProvider, prewarm_params

    p = prewarm_params(_req(cache_ttl="1h"))
    assert p["max_tokens"] == 1
    assert p["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in str(p["messages"])
    # Same tools, system and schema as the real request, so the cache entry matches.
    assert p["output_config"] == build_real(_req(cache_ttl="1h"))["output_config"]

    cap = Capture(ANTHROPIC_MSG)
    import anthropic

    client = anthropic.Anthropic(
        api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(cap))
    )
    prov = AnthropicProvider(client)
    reqs = [_req(cache_ttl="1h") for _ in range(4)] + [_req(cache_ttl="1h", effort="high") for _ in range(2)]
    assert prov.prewarm(reqs) == 1  # the second group is below the minimum size
    assert len(cap.requests) == 1


def build_real(req):
    from tariffagent.llm.anthropic_provider import build_params

    return build_params(req)


def test_batch_ids_are_valid_and_unique():
    from tariffagent.llm.anthropic_provider import BATCH_ID_OK, safe_batch_ids

    cids = ["atlas_test_00001#0", "atlas_test_00001#1", "x:y" * 40, "atlas_test_00002"]
    ids = safe_batch_ids(cids)
    assert all(BATCH_ID_OK.match(v) for v in ids.values())
    assert len(set(ids.values())) == len(cids)
