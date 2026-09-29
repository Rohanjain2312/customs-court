"""Print failed items of a run for error analysis: description, gold, prediction, reasoning, tool calls.

Usage: uv run python scripts/show_failures.py <run_id> [--level 10|8|6] [--start 0] [--count 20]
"""

import argparse
import json

from tariffagent.evals.datasets import load_dataset
from tariffagent.evals.run import load_run, traces
from tariffagent.evals.taxonomy import level_of

ap = argparse.ArgumentParser()
ap.add_argument("run_id")
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--count", type=int, default=20)
a = ap.parse_args()

results, scored, report = load_run(a.run_id)
items = {it["item_id"]: it for it in load_dataset(report["dataset"])}
res = {r["item_id"]: r for r in results}
tr = traces(a.run_id)
fails = [r for r in scored if level_of(r)]
print(f"{len(fails)} failures of {len(scored)}")
for r in fails[a.start : a.start + a.count]:
    it = items[r["item_id"]]
    cls = res[r["item_id"]].get("classification") or {}
    print("=" * 100)
    print(
        f"{r['item_id']}  level={level_of(r)}  stale={r['stale']}  abstain={r['abstain']}  conf={r['confidence']}"
    )
    print(f"DESC: {it['description'][:400]}")
    print(
        f"GOLD: {it['gold_code']} (current {it.get('gold_current')}, {it.get('crosswalk_method')})   PRED: {r['pred']}"
    )
    print(f"REF:  {(it.get('reference_reasoning') or '')[:500]}")
    print(f"GRI:  {cls.get('gri_path')}")
    print(f"WHY:  {(cls.get('rationale') or '')[:500]}")
    print(
        f"MISSING: {cls.get('missing_facts')}  REJECTED: {[x['code'] for x in cls.get('rejected_alternatives', [])]}"
    )
    print(f"CITED: {cls.get('cited_rulings')}")
    calls = [
        f"{e['tool']}({json.dumps(e['args'])[:80]})"
        for e in tr.get(r["item_id"], [])
        if e.get("type") == "tool_call"
    ]
    print(f"TOOLS: {' | '.join(calls)}")
