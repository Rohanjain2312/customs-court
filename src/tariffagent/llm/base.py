"""Provider-neutral request and response types.

Messages use the Anthropic content-block shape internally (text, tool_use,
tool_result, thinking). Other adapters translate to and from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from tariffagent.ledger import Usage


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class LLMRequest:
    model: str
    messages: list[dict]
    system: list[dict] = field(default_factory=list)  # text blocks; cache_control allowed
    tools: list[ToolSpec] = field(default_factory=list)
    max_tokens: int = 2048
    temperature: float | None = None
    thinking: dict | None = None
    effort: str | None = None
    output_schema: dict | None = None  # JSON schema for structured output
    tool_choice: dict | None = None  # only "auto" or "none" (forced choice is a 400 on Sonnet 5.5)
    cache: bool = True  # add a cache breakpoint on the last message block
    cache_ttl: str = "5m"
    purpose: str = ""
    run_id: str = "adhoc"

    def cache_payload(self, provider: str) -> dict[str, Any]:
        return {
            "provider": provider,
            "model": self.model,
            "messages": self.messages,
            "system": self.system,
            "tools": [t.__dict__ for t in self.tools],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "thinking": self.thinking,
            "effort": self.effort,
            "output_schema": self.output_schema,
            "tool_choice": self.tool_choice,
        }


@dataclass
class LLMResponse:
    content: list[dict]  # normalized blocks
    stop_reason: str
    usage: Usage
    model: str
    provider: str
    latency_s: float = 0.0
    from_cache: bool = False
    usd: float = 0.0

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def tool_uses(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class Provider(Protocol):
    name: str

    def complete(self, req: LLMRequest) -> LLMResponse: ...
