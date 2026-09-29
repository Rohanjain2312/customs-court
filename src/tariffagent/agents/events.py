"""Typed events emitted by every agent through one callback.

The eval harness records them to jsonl traces. The demo streams them over SSE and
replays them with the original timing.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class _E(BaseModel):
    t: float = 0.0  # seconds since run start
    run_id: str = ""
    agent: str = ""  # "single", "orchestrator", "advocate:4202", "adjudicator", ...


class RunStart(_E):
    type: Literal["run_start"] = "run_start"
    description: str
    arm: str
    models: dict[str, str] = {}


class FactExtracted(_E):
    type: Literal["fact_extracted"] = "fact_extracted"
    facts: dict[str, str]
    missing_facts: list[str] = []


class ToolCall(_E):
    type: Literal["tool_call"] = "tool_call"
    tool: str
    args: dict[str, Any]
    result_preview: str = ""
    ms: int = 0


class TreeFocus(_E):
    type: Literal["tree_focus"] = "tree_focus"
    code: str
    state: Literal["visited", "candidate", "rejected", "chosen"]
    reason: str = ""


class AdvocateChunk(_E):
    type: Literal["advocate_chunk"] = "advocate_chunk"
    heading: str
    text: str


class AdvocateDone(_E):
    type: Literal["advocate_done"] = "advocate_done"
    heading: str
    memo: dict[str, Any]
    tokens: int = 0
    ms: int = 0


class AdjudicatorChunk(_E):
    type: Literal["adjudicator_chunk"] = "adjudicator_chunk"
    text: str


class RulingEvent(_E):
    type: Literal["ruling"] = "ruling"
    classification: dict[str, Any]


class CostUpdate(_E):
    type: Literal["cost_update"] = "cost_update"
    usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    calls: int
    cache_hit_rate: float = 0.0


class ErrorEvent(_E):
    type: Literal["error"] = "error"
    message: str


Event = Annotated[
    RunStart | FactExtracted | ToolCall | TreeFocus | AdvocateChunk | AdvocateDone | AdjudicatorChunk | RulingEvent | CostUpdate | ErrorEvent,
    Field(discriminator="type"),
]
EventAdapter: TypeAdapter = TypeAdapter(Event)

EventCallback = Callable[[BaseModel], None]


class EventBus:
    """Stamps time and run id on events and forwards them to one callback."""

    def __init__(self, run_id: str, callback: EventCallback | None = None):
        self.run_id = run_id
        self.callback = callback
        self.t0 = time.perf_counter()
        self.events: list[BaseModel] = []

    def emit(self, ev: BaseModel) -> None:
        ev.t = round(time.perf_counter() - self.t0, 3)
        ev.run_id = self.run_id
        self.events.append(ev)
        if self.callback:
            self.callback(ev)


def event_json_schema() -> dict:
    return EventAdapter.json_schema()
