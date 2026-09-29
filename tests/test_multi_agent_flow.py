"""Multi-agent orchestration with a scripted fake model (no API calls)."""

import json

from tariffagent.agents.events import EventBus
from tariffagent.agents.multi import MultiConfig, multi_episode
from tariffagent.agents.runner import drive, run_batched
from tariffagent.ledger import Usage
from tariffagent.llm.base import LLMRequest, LLMResponse

PLAN = {
    "facts": {"material": "leather", "function": "carry items", "form": "bag", "end_use": "personal"},
    "missing_facts": [],
    "candidate_headings": ["4202", "3926"],
    "reasoning": "bag of leather",
}
FINAL = {
    "hts10": "4202.21.90.00",
    "facts": PLAN["facts"],
    "gri_path": ["GRI 1: heading 4202", "GRI 6: 4202.21"],
    "deciding_gri": "GRI 1",
    "cited_rulings": [],
    "rejected_alternatives": [{"code": "3926", "reason": "not plastic"}],
    "missing_facts": [],
    "confidence": 0.8,
    "abstain": False,
    "rationale": "Heading 4202 names handbags.",
}


def memo(h):
    return {
        "heading": h,
        "best_code": f"{h}.00.00.00",
        "argument": f"case for {h}",
        "supporting_rulings": [],
        "exclusions_against": [],
        "strength": 0.9 if h == "4202" else 0.1,
    }


def fake(req: LLMRequest) -> LLMResponse:
    p = req.purpose
    first_turn = len(req.messages) == 1
    if p.startswith("orchestrator") and first_turn:
        content = [
            {"type": "tool_use", "id": "t1", "name": "hts_search", "input": {"text": "leather handbag"}}
        ]
        stop = "tool_use"
    elif p.startswith("orchestrator"):
        content, stop = [{"type": "text", "text": json.dumps(PLAN)}], "end_turn"
    elif p.startswith("advocate-"):
        h = p.split(":")[0].split("-")[1]
        if first_turn:
            content = [
                {
                    "type": "tool_use",
                    "id": "t2",
                    "name": "get_notes",
                    "input": {"scope": "chapter", "id": h[:2]},
                }
            ]
            stop = "tool_use"
        else:
            content, stop = [{"type": "text", "text": json.dumps(memo(h))}], "end_turn"
    else:
        content, stop = [{"type": "text", "text": json.dumps(FINAL)}], "end_turn"
    return LLMResponse(
        content=content,
        stop_reason=stop,
        usage=Usage(input_tokens=100, output_tokens=20),
        model=req.model,
        provider="fake",
    )


def _episode(tools, item):
    cfg = MultiConfig.default(run_id="test-multi")
    bus = EventBus("test")
    return multi_episode(item, cfg, tools, bus), bus


def test_multi_agent_interactive(tools):
    item = {"item_id": "x1", "description": "leather handbag"}
    gen, bus = _episode(tools, item)
    res = drive(gen, complete=fake)
    assert res["classification"]["hts10"] == "4202.21.90.00"
    assert res["candidate_headings"] == ["4202", "3926"]
    assert set(res["memos"]) == {"4202", "3926"}
    types = [e.type for e in bus.events]
    for t in (
        "run_start",
        "fact_extracted",
        "tool_call",
        "tree_focus",
        "advocate_chunk",
        "advocate_done",
        "adjudicator_chunk",
        "ruling",
        "cost_update",
    ):
        assert t in types, t
    # One orchestrator (2 calls), two advocates (2 calls each), one adjudicator call.
    assert res["calls"] == 7


def test_multi_agent_batched_lockstep(tools, monkeypatch):
    from tariffagent.agents import runner

    class FakeBatch(runner.AnthropicProvider):
        def __init__(self):
            pass

        def complete(self, req):
            return fake(req)

        def complete_batch(self, reqs):
            return {cid: fake(r) for cid, r in reqs}

    monkeypatch.setattr(runner, "provider_for", lambda model: FakeBatch())
    items = [{"item_id": f"x{i}", "description": "leather handbag"} for i in range(3)]
    out = run_batched(lambda it: _episode(tools, it), items, log=lambda *_: None)
    assert all(r["classification"]["hts10"] == "4202.21.90.00" for r in out)
