"""Build a demo replay source trace from a real in-session run.

The in-session agent worked through `scripts/agent_tools.py` with `TA_LOG=<file>` set, so every
tool call it made was logged. This script turns that log plus the agent's final JSON answer
(`evals/blind/out/<run>/<item>.json`) into the typed events the demo replays: run_start, the
real tool calls, tree focus, the extracted facts and the ruling. Nothing is invented: the
timing is spread evenly over the logged milliseconds, and the cost is zero (no API spend).

    uv run python scripts/trace_from_blind.py objection-run objection_leather logs/leather.jsonl \\
        --description "..." --out demo/replays/sources/objection.traces.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from tariffagent.agents.events import (
    FactExtracted,
    RulingEvent,
    RunStart,
    ToolCall,
    TreeFocus,
)

ROOT = Path(__file__).resolve().parents[1]


def build(run: str, item: str, log: Path, description: str, model: str) -> tuple[dict, dict]:
    ans = json.loads((ROOT / "evals" / "blind" / "out" / run / f"{item}.json").read_text())
    cls = ans["classification"]
    calls = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    evs: list = [
        RunStart(
            agent="single",
            description=description,
            arm="A",
            models={"main": model},
        )
    ]
    t = 0.0
    for c in calls:
        t += max(c["ms"], 50) / 1000 + 1.2  # a model turn between tool calls, spread evenly
        ev = ToolCall(
            agent="single", tool=c["tool"], args=c["args"], result_preview=c["result_preview"], ms=c["ms"]
        )
        ev.t = round(t, 3)
        evs.append(ev)
        code = c["args"].get("code")
        if c["tool"] in ("hts_navigate", "hts_revision_diff") and code and re.sub(r"\D", "", code):
            f = TreeFocus(agent="single", code=code, state="visited")
            f.t = round(t, 3)
            evs.append(f)
    facts = cls.get("facts") or {}
    fe = FactExtracted(
        agent="single",
        facts={k: str(v) for k, v in facts.items()},
        missing_facts=cls.get("missing_facts", []),
    )
    fe.t = round(t + 0.5, 3)
    evs.append(fe)
    for alt in cls.get("rejected_alternatives", []):
        d = re.sub(r"\D", "", alt["code"])
        if d:
            r = TreeFocus(agent="single", code=alt["code"], state="rejected", reason=alt["reason"])
            r.t = round(t + 1.0, 3)
            evs.append(r)
    if cls.get("hts10"):
        ch = TreeFocus(agent="single", code=cls["hts10"], state="chosen")
        ch.t = round(t + 1.5, 3)
        evs.append(ch)
    rl = RulingEvent(agent="single", classification=cls)
    rl.t = round(t + 2.0, 3)
    evs.append(rl)
    for e in evs:
        e.run_id = f"{run}:{item}"
    trace = {"item_id": item, "events": [e.model_dump() for e in evs]}
    result = {
        "item_id": item,
        "arm": "A",
        "usd": 0.0,
        "tokens": 0,
        "calls": 0,
        "tool_calls": len(calls),
        "classification": cls,
    }
    return trace, result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("item")
    ap.add_argument("log", type=Path)
    ap.add_argument("--description", required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5 (in the Claude Code session)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    trace, result = build(a.run, a.item, a.log, a.description, a.model)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("a") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    with a.out.with_name(a.out.name.replace("traces", "results")).open("a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"{a.item}: {len(trace['events'])} events")


if __name__ == "__main__":
    main()
