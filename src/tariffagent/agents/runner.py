"""Drive agent episodes interactively or through the Batch API.

Interactive: each episode runs on its own thread, one request at a time.
Batch: all episodes advance in lockstep. Every round collects the pending request
of each live episode, sends them as one Message Batch (50% off), and feeds the
responses back. Tool calls run locally between rounds. Responses land in the same
on-disk cache, so a batch run can be replayed interactively for free.
"""

from __future__ import annotations

import concurrent.futures as cf
import traceback
from collections.abc import Callable

from tariffagent.agents.events import ErrorEvent, EventBus
from tariffagent.llm.anthropic_provider import AnthropicProvider
from tariffagent.llm.base import LLMRequest, LLMResponse
from tariffagent.llm.openai_provider import LocalProvider, OpenAIProvider

_providers: dict[str, object] = {}


def provider_for(model: str):
    if model.startswith("local-"):
        key = "local"
    elif model.startswith(("gpt", "o1", "o3", "o4")):
        key = "openai"
    else:
        key = "anthropic"
    if key not in _providers:
        _providers[key] = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "local": LocalProvider}[
            key
        ]()
    return _providers[key]


def _call(req: LLMRequest, complete) -> LLMResponse:
    return (complete or provider_for(req.model).complete)(req)


def drive(episode, complete: Callable[[LLMRequest], LLMResponse] | None = None) -> dict:
    """Run one episode to completion with interactive calls.

    An episode may yield a list of requests (parallel sub-agents); they run concurrently.
    """
    try:
        req = next(episode)
        while True:
            if isinstance(req, list):
                with cf.ThreadPoolExecutor(max_workers=max(1, len(req))) as ex:
                    resp = list(ex.map(lambda r: _call(r, complete), req))
            else:
                resp = _call(req, complete)
            req = episode.send(resp)
    except StopIteration as stop:
        return stop.value


def run_interactive(
    make_episode: Callable[[dict], tuple], items: list[dict], concurrency: int = 4
) -> list[dict]:
    """make_episode(item) -> (generator, bus). Returns result dicts with events attached."""

    def one(item):
        gen, bus = make_episode(item)
        try:
            res = drive(gen)
        except Exception as e:  # noqa: BLE001
            bus.emit(ErrorEvent(message=str(e)[:500]))
            res = {
                "item_id": item["item_id"],
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()[-2000:],
            }
        res["events"] = [ev.model_dump() for ev in bus.events]
        c = (res.get("classification") or {}).get("hts10")
        print(
            f"done {item['item_id']} -> {c} ${res.get('usd', 0):.4f} {res.get('error', '')[:120]}", flush=True
        )
        return res

    with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
        return list(ex.map(one, items))


def run_batched(
    make_episode: Callable[[dict], tuple], items: list[dict], max_rounds: int = 40, log=print
) -> list[dict]:
    """Lockstep batch execution. Anthropic models only (OpenAI falls back to interactive)."""
    live: dict[str, tuple] = {}
    pending: dict[str, LLMRequest] = {}
    done: dict[str, dict] = {}
    buses: dict[str, EventBus] = {}
    for it in items:
        gen, bus = make_episode(it)
        buses[it["item_id"]] = bus
        try:
            pending[it["item_id"]] = next(gen)
            live[it["item_id"]] = gen
        except StopIteration as s:
            done[it["item_id"]] = s.value
    rnd = 0
    while pending and rnd < max_rounds:
        rnd += 1
        by_provider: dict[str, list[tuple[str, LLMRequest]]] = {}
        flat: dict[str, LLMRequest] = {}
        for iid, req in pending.items():
            if isinstance(req, list):
                for j, r in enumerate(req):
                    flat[f"{iid}#{j}"] = r
            else:
                flat[iid] = req
        for fid, req in flat.items():
            by_provider.setdefault(type(provider_for(req.model)).__name__, []).append((fid, req))
        responses: dict[str, LLMResponse | Exception] = {}
        for reqs in by_provider.values():
            prov = provider_for(reqs[0][1].model)
            if isinstance(prov, AnthropicProvider):
                log(f"round {rnd}: batch of {len(reqs)} requests")
                responses.update(prov.complete_batch(reqs))
            else:
                for iid, req in reqs:
                    try:
                        responses[iid] = prov.complete(req)
                    except Exception as e:  # noqa: BLE001
                        responses[iid] = e
        new_pending: dict[str, LLMRequest] = {}
        # One interactive retry for requests the batch could not serve.
        for fid, resp in list(responses.items()):
            if isinstance(resp, Exception):
                try:
                    responses[fid] = provider_for(flat[fid].model).complete(flat[fid])
                except Exception as e:  # noqa: BLE001
                    responses[fid] = e
        for iid, req in pending.items():
            gen = live[iid]
            if isinstance(req, list):
                resp = [responses[f"{iid}#{j}"] for j in range(len(req))]
                failed = next((r for r in resp if isinstance(r, Exception)), None)
            else:
                resp = responses[iid]
                failed = resp if isinstance(resp, Exception) else None
            if failed is not None:
                buses[iid].emit(ErrorEvent(message=str(failed)[:500]))
                done[iid] = {"item_id": iid, "error": f"{type(failed).__name__}: {failed}"}
                live.pop(iid)
                continue
            try:
                new_pending[iid] = gen.send(resp)
            except StopIteration as s:
                done[iid] = s.value
                live.pop(iid)
            except Exception as e:  # noqa: BLE001
                done[iid] = {
                    "item_id": iid,
                    "error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-2000:],
                }
                live.pop(iid)
        pending = new_pending
    for iid in pending:
        done[iid] = {"item_id": iid, "error": "max rounds reached"}
    out = []
    for it in items:
        r = done[it["item_id"]]
        r["events"] = [ev.model_dump() for ev in buses[it["item_id"]].events]
        out.append(r)
    return out
