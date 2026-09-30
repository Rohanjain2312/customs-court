"""Score a blind in-session run (Claude working inside Claude Code as the agent) like any other run.

Reads evals/blind/out/<run_id>/<item_id>.json, validates each classification against the
same schema, writes evals/runs/<run_id>/{results,scored}.jsonl and evals/reports/<run_id>.json.
No API calls: the classifications were produced in the Claude Code session, which is covered
by the user's plan, so the run is logged at $0 of API spend.

    uv run python scripts/score_blind.py cc-subset80-A --dataset atlas_test_200 --items-from subset_80
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from tariffagent.agents.schemas import Classification
from tariffagent.config import get_settings
from tariffagent.evals.datasets import MANIFEST, load_dataset
from tariffagent.evals.metrics import score_run
from tariffagent.evals.run import REPORTS, RUNS, SEED, git_sha
from tariffagent.evals.stats import bootstrap_ci

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = {
    "A": (
        "Blind: the classifying agents read only a descriptions-only file "
        "(evals/blind/*.jsonl), the skill, and a tool CLI backed by the MCP server with "
        "--redact-eval. Gold labels stayed in files they were told never to open. "
        "Same skill workflow, final checks and output schema as arm A."
    ),
    "Z": (
        "Blind zero-shot control: one agent read only the descriptions-only file and the skill, "
        "with no lookup tools, and wrote the same output schema from its own knowledge."
    ),
}


def later_citations(items: list[dict], results: list[dict]) -> list[dict]:
    """Cited rulings dated after the item's own ruling: precedent a broker could not have had."""
    dated = {it["item_id"]: it["ruling_date"] for it in items if it.get("ruling_date")}
    if not dated:
        return []
    con = sqlite3.connect(f"file:{get_settings().db_path}?mode=ro", uri=True)
    out = []
    for r in results:
        gold_date = dated.get(r["item_id"])
        for c in (r.get("classification") or {}).get("cited_rulings", []):
            row = con.execute("SELECT date FROM rulings WHERE id = ?", (c["id"],)).fetchone()
            if gold_date and row and row[0] and row[0] > gold_date:
                out.append(
                    {"item_id": r["item_id"], "cited": c["id"], "cited_date": row[0], "item_date": gold_date}
                )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--items-from", default="")
    ap.add_argument("--model", default="claude-opus-5-5 (in the Claude Code session, not the API)")
    ap.add_argument("--arm", default="A", choices=["A", "Z"])
    a = ap.parse_args()
    items = load_dataset(a.dataset)
    if a.items_from:
        keep = {it["item_id"] for it in load_dataset(a.items_from)}
        items = [it for it in items if it["item_id"] in keep]
    src = ROOT / "evals" / "blind" / "out" / a.run_id
    results = []
    for it in items:
        p = src / f"{it['item_id']}.json"
        r = {"item_id": it["item_id"], "arm": a.arm, "usd": 0.0, "tokens": 0, "calls": 0}
        if not p.exists():
            r.update(classification=None, error="no output file")
        else:
            raw = json.loads(p.read_text())
            try:
                cls = Classification.model_validate(raw["classification"])
                r.update(classification=cls.model_dump(), parse_error="")
            except Exception as e:  # noqa: BLE001
                r.update(classification=None, parse_error=f"invalid classification: {str(e)[:200]}")
            r["tool_calls"] = int(raw.get("tool_calls") or 0)
            r["tools"] = raw.get("tools", [])
        results.append(r)
    out = RUNS / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    rows, agg = score_run(items, results)
    with (out / "scored.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    cis = {
        k: bootstrap_ci([r[k] for r in rows if r[k] is not None], seed=SEED)
        for k in ("exact_10", "exact_8", "exact_6", "exact_4", "exact_2")
    }
    later = later_citations(items, results)
    drop = {x["item_id"] for x in later}
    sens = None
    if drop:
        sens = {
            "note": "exact_10 leaving out items that cite a ruling dated after the item's own ruling",
            "excluded": sorted(drop),
            "exact_10": bootstrap_ci(
                [r["exact_10"] for r in rows if r["exact_10"] is not None and r["item_id"] not in drop],
                seed=SEED,
            ),
        }
    man = json.loads(MANIFEST.read_text())
    report = {
        "run_id": a.run_id,
        "dataset": a.dataset,
        "dataset_sha256": man[a.dataset]["sha256"],
        "items_from": a.items_from,
        "arm": a.arm,
        "mode": "agent-in-session" if a.arm == "A" else "zero-shot-in-session",
        "n_items": len(items),
        "n_with_output": sum(1 for r in results if r.get("classification")),
        "git_sha": git_sha(),
        "seed": SEED,
        "models": {"main": a.model},
        "protocol": PROTOCOL[a.arm],
        "redact_eval": a.arm == "A",
        "scored_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "metrics": agg,
        "ci95": cis,
        "later_dated_citations": later,
        "sensitivity_without_later_citations": sens,
        "cost_note": "No API spend: produced in the Claude Code session (covered by the user's plan).",
    }
    (REPORTS / f"{a.run_id}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: cis[k] for k in ("exact_10", "exact_6", "exact_4")}, indent=1))
    print("with output:", report["n_with_output"], "of", len(items), "| abstain", agg["abstain_rate"])


if __name__ == "__main__":
    main()
