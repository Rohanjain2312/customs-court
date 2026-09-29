"""Anthropic Messages API adapter with prompt caching, structured output,
the on-disk response cache, the spend ledger and Message Batches."""

from __future__ import annotations

import copy
import json
import time

from tariffagent.cache import ResponseCache, request_key
from tariffagent.config import get_settings, price_for
from tariffagent.ledger import Usage, check_budget, cost_usd, record
from tariffagent.llm.base import LLMRequest, LLMResponse


class OfflineMiss(RuntimeError):
    """Raised in offline mode when a request is not in the response cache."""


def estimate_usd(req: LLMRequest, batch: bool = False) -> float:
    """Conservative upper estimate: all input uncached, full max_tokens output."""
    chars = len(json.dumps(req.messages)) + len(json.dumps(req.system)) + len(json.dumps([t.__dict__ for t in req.tools]))
    p = price_for(req.model)
    usd = (chars / 3.0) * p.input / 1e6 + req.max_tokens * p.output / 1e6
    return usd * (p.batch_discount if batch else 1.0)


def usage_from(u) -> Usage:
    cc = getattr(u, "cache_creation", None)
    w5 = getattr(cc, "ephemeral_5m_input_tokens", None) if cc else None
    w1 = getattr(cc, "ephemeral_1h_input_tokens", None) if cc else None
    total_w = u.cache_creation_input_tokens or 0
    if w5 is None and w1 is None:
        w5, w1 = total_w, 0
    return Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0,
        cache_write_5m_tokens=w5 or 0,
        cache_write_1h_tokens=w1 or 0,
    )


def build_params(req: LLMRequest, for_batch: bool = False) -> dict:
    """Build messages.create kwargs.

    SDK 1.x dropped `temperature` from the method signature. Haiku 4.5 still honours
    it, so it goes through extra_body (or straight into a batch request's params).
    Sonnet 5.5 rejects non-default values, so callers leave it unset there.
    """
    cc = {"type": "ephemeral"} if req.cache_ttl == "5m" else {"type": "ephemeral", "ttl": req.cache_ttl}
    system = copy.deepcopy(req.system)
    messages = copy.deepcopy(req.messages)
    if req.cache:
        # Breakpoint 1: end of the static prefix (tools + system).
        if system:
            system[-1]["cache_control"] = cc
        # Breakpoint 2: end of the conversation so far, so the next turn reads it.
        if messages:
            last = messages[-1]
            if isinstance(last["content"], str):
                last["content"] = [{"type": "text", "text": last["content"]}]
            for b in reversed(last["content"]):
                if b.get("type") in ("text", "tool_result", "tool_use", "image", "document"):
                    b["cache_control"] = cc
                    break
    params: dict = {"model": req.model, "max_tokens": req.max_tokens, "messages": messages}
    if system:
        params["system"] = system
    if req.tools:
        params["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in req.tools
        ]
    if req.tool_choice is not None:
        params["tool_choice"] = req.tool_choice
    if req.temperature is not None:
        if for_batch:
            params["temperature"] = req.temperature
        else:
            params["extra_body"] = {"temperature": req.temperature}
    if req.thinking is not None:
        params["thinking"] = req.thinking
    oc: dict = {}
    if req.effort:
        oc["effort"] = req.effort
    if req.output_schema:
        oc["format"] = {"type": "json_schema", "schema": req.output_schema}
    if oc:
        params["output_config"] = oc
    return params


def normalize_content(blocks) -> list[dict]:
    out = []
    for b in blocks:
        d = b.model_dump(mode="json", exclude_none=True)
        # Fields the API returns but does not accept back.
        d.pop("citations", None) if not d.get("citations") else None
        d.pop("caller", None)
        out.append(d)
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client=None):
        self._client = client
        self.cache = ResponseCache()

    @property
    def client(self):
        if self._client is None:
            import anthropic

            s = get_settings()
            if not s.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            self._client = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=4, timeout=300)
        return self._client

    def _key(self, req: LLMRequest) -> str:
        return request_key(req.cache_payload(self.name))

    def cached(self, req: LLMRequest) -> LLMResponse | None:
        hit = self.cache.get(self._key(req))
        if hit is None:
            return None
        return LLMResponse(
            content=hit["content"],
            stop_reason=hit["stop_reason"],
            usage=Usage(**hit["usage"]),
            model=hit["model"],
            provider=self.name,
            latency_s=hit.get("latency_s", 0.0),
            from_cache=True,
            usd=hit.get("usd", 0.0),
        )

    def _store(self, req: LLMRequest, resp: LLMResponse, batch: bool) -> None:
        self.cache.put(
            self._key(req),
            {
                "content": resp.content,
                "stop_reason": resp.stop_reason,
                "usage": resp.usage.__dict__,
                "model": resp.model,
                "latency_s": resp.latency_s,
                "usd": resp.usd,
                "batch": batch,
            },
        )

    def complete(self, req: LLMRequest) -> LLMResponse:
        hit = self.cached(req)
        if hit:
            return hit
        s = get_settings()
        if s.offline:
            raise OfflineMiss(f"offline mode and no cached response for {req.purpose}")
        check_budget(req.run_id, estimate_usd(req))
        t0 = time.perf_counter()
        m = self.client.messages.create(**build_params(req))
        dt = time.perf_counter() - t0
        u = usage_from(m.usage)
        e = record(provider=self.name, model=req.model, usage=u, run_id=req.run_id, purpose=req.purpose, latency_s=dt)
        resp = LLMResponse(
            content=normalize_content(m.content),
            stop_reason=m.stop_reason or "",
            usage=u,
            model=m.model,
            provider=self.name,
            latency_s=dt,
            usd=e.usd,
        )
        self._store(req, resp, batch=False)
        return resp

    # ---------- Message Batches ----------
    def complete_batch(self, items: list[tuple[str, LLMRequest]], poll_s: float = 20.0, max_wait_s: float = 6 * 3600) -> dict[str, LLMResponse | Exception]:
        """Run many independent requests through the Batch API (50% off). Cached ones are skipped."""
        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request

        out: dict[str, LLMResponse | Exception] = {}
        todo: list[tuple[str, LLMRequest]] = []
        for cid, req in items:
            hit = self.cached(req)
            if hit:
                out[cid] = hit
            else:
                todo.append((cid, req))
        if not todo:
            return out
        s = get_settings()
        if s.offline:
            for cid, req in todo:
                out[cid] = OfflineMiss(f"offline and uncached: {req.purpose}")
            return out
        run_id = todo[0][1].run_id
        check_budget(run_id, sum(estimate_usd(r, batch=True) for _, r in todo))
        by_id = dict(todo)
        batch = self.client.messages.batches.create(
            requests=[Request(custom_id=cid, params=MessageCreateParamsNonStreaming(**build_params(r, for_batch=True))) for cid, r in todo]
        )
        t0 = time.time()
        while True:
            b = self.client.messages.batches.retrieve(batch.id)
            if b.processing_status == "ended":
                break
            if time.time() - t0 > max_wait_s:
                self.client.messages.batches.cancel(batch.id)
                raise TimeoutError(f"batch {batch.id} did not finish in {max_wait_s}s")
            time.sleep(poll_s)
        elapsed = time.time() - t0
        for res in self.client.messages.batches.results(batch.id):
            req = by_id[res.custom_id]
            if res.result.type != "succeeded":
                out[res.custom_id] = RuntimeError(f"batch item {res.result.type}: {getattr(res.result, 'error', '')}")
                continue
            m = res.result.message
            u = usage_from(m.usage)
            e = record(
                provider=self.name, model=req.model, usage=u, run_id=req.run_id, purpose=req.purpose, batch=True,
                extra={"batch_id": batch.id},
            )
            resp = LLMResponse(
                content=normalize_content(m.content),
                stop_reason=m.stop_reason or "",
                usage=u,
                model=m.model,
                provider=self.name,
                latency_s=0.0,
                usd=e.usd,
            )
            self._store(req, resp, batch=True)
            out[res.custom_id] = resp
        for cid in by_id:
            out.setdefault(cid, RuntimeError("missing from batch results"))
        _ = elapsed
        return out


def dollars(model: str, u: Usage, batch: bool = False) -> float:
    return cost_usd(model, u, batch)
