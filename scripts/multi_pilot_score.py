"""Score the in-session multi-agent pilot against the single agent on the same items.

The pilot (20 items drawn with seed 13 from subset_80) ran in the Claude Code session on Claude
Sonnet 5.5: orchestrator agents wrote plans (evals/blind/multi/plan), one advocate agent per item
argued each of the first three headings separately (evals/blind/multi/memos), and adjudicator
agents wrote the final answers (evals/blind/out/cc-multi20-D). The comparison arm is the
date-limited single agent (cc-subset80-A-asof) on the same items. No API spend.

    uv run python scripts/multi_pilot_score.py
"""

from __future__ import annotations

import json
import random

from tariffagent.agents.schemas import Classification
from tariffagent.config import ROOT
from tariffagent.evals.datasets import load_dataset
from tariffagent.evals.metrics import score_run
from tariffagent.evals.stats import paired_diff


def sample_ids() -> list[str]:
    ids = [json.loads(line)["item_id"] for line in (ROOT / "evals" / "blind" / "subset_80.jsonl").open()]
    return sorted(random.Random(13).sample(ids, 20))


def score(name: str, items: list[dict]) -> tuple[dict, dict]:
    res = []
    for it in items:
        raw = json.loads((ROOT / "evals" / "blind" / "out" / name / f"{it['item_id']}.json").read_text())
        cls = Classification.model_validate(raw["classification"])
        res.append(
            {
                "item_id": it["item_id"],
                "arm": "A",
                "usd": 0.0,
                "tokens": 0,
                "calls": 0,
                "classification": cls.model_dump(),
                "tool_calls": raw.get("tool_calls") or 0,
            }
        )
    rows, agg = score_run(items, res)
    return {r["item_id"]: r for r in rows}, agg


def main() -> None:
    ids = sample_ids()
    items = [it for it in load_dataset("atlas_test_200") if it["item_id"] in set(ids)]
    multi, am = score("cc-multi20-D", items)
    single, asg = score("cc-subset80-A-asof", items)
    out: dict = {
        "note": "Pilot: 20 items, in-session Claude Sonnet 5.5, advocates one agent per item. Intervals are wide.",
        "items": len(ids),
        "item_ids": ids,
    }
    for tag, rows, agg in (("multi", multi, am), ("single", single, asg)):
        out[tag] = {"abstain_rate": agg["abstain_rate"]}
        for k in (10, 6, 4):
            v = [float(rows[i][f"exact_{k}"]) for i in ids if rows[i][f"exact_{k}"] is not None]
            out[tag][f"acc_{k}"] = {"mean": round(sum(v) / len(v), 4), "n": len(v)}
    for k in (10, 6):
        a = {i: float(single[i][f"exact_{k}"]) for i in ids if single[i][f"exact_{k}"] is not None}
        b = {i: float(multi[i][f"exact_{k}"]) for i in ids if multi[i][f"exact_{k}"] is not None}
        out[f"multi_minus_single_acc{k}"] = paired_diff(a, b)
    (ROOT / "evals" / "reports" / "multi20_pilot.json").write_text(json.dumps(out, indent=2))
    print(
        json.dumps(
            {k: out[k] for k in ("multi", "single", "multi_minus_single_acc10", "multi_minus_single_acc6")},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
