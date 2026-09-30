"""OpenAI Chat Completions adapter behind the same interface.

Used only for the cheap provider comparison on a subset. It translates the
internal Anthropic-shaped messages to Chat Completions and back. OpenAI caches
long prompt prefixes automatically; cached tokens are read from
usage.prompt_tokens_details.cached_tokens and logged as cache reads.
"""

from __future__ import annotations

import json
import time

from tariffagent.cache import ResponseCache, request_key
from tariffagent.config import get_settings
from tariffagent.ledger import Usage, check_budget, record
from tariffagent.llm.anthropic_provider import OfflineMiss, estimate_usd
from tariffagent.llm.base import LLMRequest, LLMResponse


def to_openai_messages(req: LLMRequest) -> list[dict]:
    out: list[dict] = []
    sys_text = "\n\n".join(b["text"] for b in req.system if b.get("type") == "text")
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for m in req.messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "assistant":
            text = "".join(b.get("text", "") for b in content if b["type"] == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                }
                for b in content
                if b["type"] == "tool_use"
            ]
            msg: dict = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            texts = []
            for b in content:
                if b["type"] == "tool_result":
                    c = b["content"]
                    if isinstance(c, list):
                        c = "".join(x.get("text", "") for x in c)
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": c})
                elif b["type"] == "text":
                    texts.append(b["text"])
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
    return out


class OpenAIProvider:
    name = "openai"

    def __init__(self, client=None):
        self._client = client
        self.cache = ResponseCache()

    @property
    def client(self):
        if self._client is None:
            import openai

            s = get_settings()
            if not s.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            self._client = openai.OpenAI(api_key=s.openai_api_key, max_retries=4, timeout=300)
        return self._client

    def build_params(self, req: LLMRequest) -> dict:
        p: dict = {
            "model": req.model,
            "messages": to_openai_messages(req),
            "max_completion_tokens": req.max_tokens,
        }
        if req.tools:
            p["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
                }
                for t in req.tools
            ]
        if req.output_schema:
            p["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": req.output_schema, "strict": True},
            }
        p["reasoning_effort"] = req.effort or "low"
        return p

    def complete(self, req: LLMRequest) -> LLMResponse:
        key = request_key(req.cache_payload(self.name))
        hit = self.cache.get(key)
        if hit:
            return LLMResponse(
                content=hit["content"],
                stop_reason=hit["stop_reason"],
                usage=Usage(**hit["usage"]),
                model=hit["model"],
                provider=self.name,
                latency_s=hit.get("latency_s", 0),
                from_cache=True,
                usd=hit.get("usd", 0.0),
            )
        if get_settings().offline:
            raise OfflineMiss(f"offline and uncached: {req.purpose}")
        check_budget(req.run_id, estimate_usd(req))
        t0 = time.perf_counter()
        r = self.client.chat.completions.create(**self.build_params(req))
        dt = time.perf_counter() - t0
        ch = r.choices[0]
        content: list[dict] = []
        if ch.message.content:
            content.append({"type": "text", "text": ch.message.content})
        for tc in ch.message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            content.append({"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args})
        cached = (r.usage.prompt_tokens_details.cached_tokens or 0) if r.usage.prompt_tokens_details else 0
        u = Usage(
            input_tokens=r.usage.prompt_tokens - cached,
            output_tokens=r.usage.completion_tokens,
            cache_read_tokens=cached,
        )
        e = record(
            provider=self.name, model=req.model, usage=u, run_id=req.run_id, purpose=req.purpose, latency_s=dt
        )
        stop = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens"}.get(
            ch.finish_reason, ch.finish_reason
        )
        resp = LLMResponse(
            content=content,
            stop_reason=stop,
            usage=u,
            model=r.model,
            provider=self.name,
            latency_s=dt,
            usd=e.usd,
        )
        self.cache.put(
            key,
            {
                "content": content,
                "stop_reason": stop,
                "usage": u.__dict__,
                "model": r.model,
                "latency_s": dt,
                "usd": e.usd,
            },
        )
        return resp


class LocalProvider(OpenAIProvider):
    """An open-weights model served on this machine by llama.cpp (`llama-server`), OpenAI-compatible.

    Costs nothing: no API key, no network, $0 in the ledger. Added on 2026-09-29 when the
    project's API budget ran out. Model ids start with `local-` (for example
    `local-qwen3.5-4b`); each id maps to its own server port in LOCAL_ENDPOINTS.
    llama.cpp cannot combine a tool list with a JSON-schema grammar, so the schema is
    enforced only on turns without tools; other turns rely on the prompt, the regex
    parser and the checked final step.
    """

    name = "local"

    def __init__(self, client=None):
        super().__init__(client)
        self._clients: dict[str, object] = {}

    def client_for(self, model: str):
        if self._client is not None:
            return self._client
        if model not in self._clients:
            import openai

            base = get_settings().local_endpoint(model)
            self._clients[model] = openai.OpenAI(base_url=base, api_key="local", max_retries=2, timeout=1800)
        return self._clients[model]

    def build_params(self, req: LLMRequest) -> dict:
        p = super().build_params(req)
        p.pop("reasoning_effort", None)
        p["max_tokens"] = p.pop("max_completion_tokens")
        tools_active = bool(req.tools) and (req.tool_choice or {}).get("type") != "none"
        if tools_active:
            p.pop("response_format", None)
        elif req.tools:
            # Final forced turn: no tools offered, so the JSON schema can be enforced.
            p.pop("tools", None)
        s = get_settings()
        # Qwen's recommended sampling for instruct (non-thinking) mode, from the model card.
        p["temperature"] = s.local_temperature
        p["top_p"] = 0.8
        p["presence_penalty"] = 1.5
        p["extra_body"] = {"top_k": 20, "chat_template_kwargs": {"enable_thinking": s.local_thinking}}
        return p

    def complete(self, req: LLMRequest) -> LLMResponse:
        # Same cache and ledger path as OpenAI, with the local client and no budget gate ($0).
        key = request_key(req.cache_payload(self.name))
        hit = self.cache.get(key)
        if hit:
            return LLMResponse(
                content=hit["content"],
                stop_reason=hit["stop_reason"],
                usage=Usage(**hit["usage"]),
                model=hit["model"],
                provider=self.name,
                latency_s=hit.get("latency_s", 0),
                from_cache=True,
                usd=0.0,
            )
        if get_settings().offline:
            raise OfflineMiss(f"offline and uncached: {req.purpose}")
        t0 = time.perf_counter()
        r = self.client_for(req.model).chat.completions.create(**self.build_params(req))
        dt = time.perf_counter() - t0
        ch = r.choices[0]
        content: list[dict] = []
        if ch.message.content:
            content.append({"type": "text", "text": ch.message.content})
        for i, tc in enumerate(ch.message.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            content.append(
                {"type": "tool_use", "id": tc.id or f"call_{i}", "name": tc.function.name, "input": args}
            )
        cached = 0
        details = getattr(r.usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        u = Usage(
            input_tokens=max(0, r.usage.prompt_tokens - cached),
            output_tokens=r.usage.completion_tokens,
            cache_read_tokens=cached,
        )
        record(
            provider=self.name, model=req.model, usage=u, run_id=req.run_id, purpose=req.purpose, latency_s=dt
        )
        stop = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens"}.get(
            ch.finish_reason, ch.finish_reason
        )
        if content and any(b["type"] == "tool_use" for b in content):
            stop = "tool_use"
        resp = LLMResponse(
            content=content,
            stop_reason=stop,
            usage=u,
            model=req.model,
            provider=self.name,
            latency_s=dt,
            usd=0.0,
        )
        self.cache.put(
            key,
            {
                "content": content,
                "stop_reason": stop,
                "usage": u.__dict__,
                "model": req.model,
                "latency_s": dt,
                "usd": 0.0,
            },
        )
        return resp


class MistralProvider(LocalProvider):
    """Mistral's API on the free "Experiment" plan (OpenAI-compatible chat completions).

    Added 2026-09-30 as a zero-cost path after the paid budget ran out. The free plan is
    rate-limited, so requests are spaced by MISTRAL_RPS and 429s are retried with backoff.
    Logged at $0 because the plan is free; prompts contain only public CBP and HTS text.
    """

    name = "mistral"
    _lock = __import__("threading").Lock()
    _last = 0.0

    def client_for(self, model: str):
        if self._client is not None:
            return self._client
        if "mistral" not in self._clients:
            import openai

            s = get_settings()
            if not s.mistral_api_key:
                raise RuntimeError("MISTRAL_API_KEY is not set")
            self._clients["mistral"] = openai.OpenAI(
                base_url="https://api.mistral.ai/v1", api_key=s.mistral_api_key, max_retries=10, timeout=600
            )
        return self._clients["mistral"]

    def build_params(self, req: LLMRequest) -> dict:
        p = LocalProvider.build_params(self, req)
        p.pop("extra_body", None)
        p.pop("top_p", None)
        p.pop("presence_penalty", None)
        p["temperature"] = get_settings().mistral_temperature
        if p.get("tool_choice", {}) == {"type": "none"}:
            p["tool_choice"] = "none"
        return p

    def complete(self, req: LLMRequest) -> LLMResponse:
        key = request_key(req.cache_payload(self.name))
        if self.cache.get(key) is None and not get_settings().offline:
            gap = 1.0 / max(0.01, get_settings().mistral_rps)
            with MistralProvider._lock:
                wait = MistralProvider._last + gap - time.time()
                if wait > 0:
                    time.sleep(wait)
                MistralProvider._last = time.time()
        return super().complete(req)
