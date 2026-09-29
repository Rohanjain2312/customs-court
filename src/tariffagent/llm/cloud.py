"""Amazon Bedrock and Google Vertex AI adapters.

These are deploy-ready code paths. They are never called live in this project,
because Bedrock and Vertex bill outside the two allowed vendors. Tests exercise
them with mocked HTTP transports and recorded response bodies. Building a real
client requires I_ACCEPT_CLOUD_COSTS=yes.
"""

from __future__ import annotations

import os
import time

from tariffagent.ledger import Usage
from tariffagent.llm.anthropic_provider import build_params, normalize_content, usage_from
from tariffagent.llm.base import LLMRequest, LLMResponse

BEDROCK_MODEL_IDS = {
    "claude-sonnet-5": "anthropic.claude-sonnet-5",
    "claude-sonnet-5-5": "anthropic.claude-sonnet-5-5",
    "claude-haiku-4-5": "anthropic.claude-haiku-4-5",
}
VERTEX_MODEL_IDS = {
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-sonnet-5-5": "claude-sonnet-5-5",
    "claude-haiku-4-5": "claude-haiku-4-5@20251001",
}


class CloudCostGuard(RuntimeError):
    pass


def require_cloud_opt_in() -> None:
    if os.environ.get("I_ACCEPT_CLOUD_COSTS") != "yes":
        raise CloudCostGuard(
            "Refusing to create a real Bedrock or Vertex client. These calls bill outside the allowed "
            "vendors. Set I_ACCEPT_CLOUD_COSTS=yes only if you intend to pay for them."
        )


class _ClaudeCloudProvider:
    name = "cloud"
    model_ids: dict[str, str] = {}

    def __init__(self, client):
        self.client = client

    def complete(self, req: LLMRequest) -> LLMResponse:
        params = build_params(req)
        params["model"] = self.model_ids.get(req.model, req.model)
        t0 = time.perf_counter()
        m = self.client.messages.create(**params)
        dt = time.perf_counter() - t0
        return LLMResponse(
            content=normalize_content(m.content),
            stop_reason=m.stop_reason or "",
            usage=usage_from(m.usage),
            model=m.model,
            provider=self.name,
            latency_s=dt,
        )


class BedrockProvider(_ClaudeCloudProvider):
    """Claude on Amazon Bedrock through the Messages-API (Mantle) endpoint.

    Prompt caching uses the same cache_control blocks (up to 4 checkpoints) and
    structured output uses output_config.format, both supported on Bedrock.
    """

    name = "bedrock"
    model_ids = BEDROCK_MODEL_IDS

    @classmethod
    def from_env(cls, region: str | None = None) -> BedrockProvider:
        require_cloud_opt_in()
        from anthropic import AnthropicBedrockMantle

        return cls(AnthropicBedrockMantle(aws_region=region or os.environ.get("AWS_REGION", "us-east-1")))


class VertexClaudeProvider(_ClaudeCloudProvider):
    """Claude on Google Vertex AI (prompt caching, tool use and structured output supported)."""

    name = "vertex"
    model_ids = VERTEX_MODEL_IDS

    @classmethod
    def from_env(cls, project_id: str | None = None, region: str = "global") -> VertexClaudeProvider:
        require_cloud_opt_in()
        from anthropic import AnthropicVertex

        return cls(
            AnthropicVertex(project_id=project_id or os.environ["GOOGLE_CLOUD_PROJECT"], region=region)
        )


class VertexGeminiProvider:
    """Gemini on Vertex AI via the generateContent REST API.

    Translates the internal message format to Gemini `contents` with
    functionDeclarations. `transport` is an httpx client; tests pass a mock.
    """

    name = "vertex-gemini"

    def __init__(
        self, http, project: str, region: str = "global", model: str = "gemini-2.5-flash", token: str = ""
    ):
        self.http = http
        self.project = project
        self.region = region
        self.model = model
        self.token = token

    @classmethod
    def from_env(cls, model: str = "gemini-2.5-flash") -> VertexGeminiProvider:
        require_cloud_opt_in()
        import subprocess

        import httpx

        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        return cls(httpx.Client(timeout=120), os.environ["GOOGLE_CLOUD_PROJECT"], model=model, token=token)

    def url(self) -> str:
        host = (
            "aiplatform.googleapis.com"
            if self.region == "global"
            else f"{self.region}-aiplatform.googleapis.com"
        )
        return (
            f"https://{host}/v1/projects/{self.project}/locations/{self.region}/publishers/google/models/"
            f"{self.model}:generateContent"
        )

    @staticmethod
    def to_body(req: LLMRequest) -> dict:
        contents = []
        for m in req.messages:
            role = "model" if m["role"] == "assistant" else "user"
            blocks = (
                m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
            )
            parts = []
            for b in blocks:
                if b["type"] == "text":
                    parts.append({"text": b["text"]})
                elif b["type"] == "tool_use":
                    parts.append({"functionCall": {"name": b["name"], "args": b["input"]}})
                elif b["type"] == "tool_result":
                    c = (
                        b["content"]
                        if isinstance(b["content"], str)
                        else "".join(x.get("text", "") for x in b["content"])
                    )
                    parts.append(
                        {"functionResponse": {"name": b.get("name", "tool"), "response": {"content": c}}}
                    )
            if parts:
                contents.append({"role": role, "parts": parts})
        body: dict = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": req.max_tokens, "temperature": 0},
        }
        sys_text = "\n\n".join(b["text"] for b in req.system if b.get("type") == "text")
        if sys_text:
            body["systemInstruction"] = {"parts": [{"text": sys_text}]}
        if req.tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.input_schema}
                        for t in req.tools
                    ]
                }
            ]
        if req.output_schema and not req.tools:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseJsonSchema"] = req.output_schema
        return body

    def complete(self, req: LLMRequest) -> LLMResponse:
        t0 = time.perf_counter()
        r = self.http.post(
            self.url(), json=self.to_body(req), headers={"Authorization": f"Bearer {self.token}"}
        )
        r.raise_for_status()
        d = r.json()
        dt = time.perf_counter() - t0
        cand = d["candidates"][0]
        content: list[dict] = []
        for i, p in enumerate(cand.get("content", {}).get("parts", [])):
            if "text" in p:
                content.append({"type": "text", "text": p["text"]})
            elif "functionCall" in p:
                fc = p["functionCall"]
                content.append(
                    {"type": "tool_use", "id": f"call_{i}", "name": fc["name"], "input": fc.get("args", {})}
                )
        um = d.get("usageMetadata", {})
        cached = um.get("cachedContentTokenCount", 0)
        u = Usage(
            input_tokens=um.get("promptTokenCount", 0) - cached,
            output_tokens=um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0),
            cache_read_tokens=cached,
        )
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        return LLMResponse(
            content=content, stop_reason=stop, usage=u, model=self.model, provider=self.name, latency_s=dt
        )
