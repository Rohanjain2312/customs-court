"""Find the source ruling of every ATLAS test item, hide it, and date the item.

1. Validates the linker on fresh_150, where the true ruling is known.
2. Links atlas_test_200 and writes evals/datasets/source_links.json (committed).
3. With --apply, adds the candidates to `eval_redactions` in the local database so the tools hide
   them (union with the older links), and rewrites evals/datasets/as_of.json.

    uv run python scripts/build_source_links.py --apply
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from tariffagent.config import ROOT
from tariffagent.data import atlas
from tariffagent.data.db import connect
from tariffagent.evals.datasets import DS_DIR

MIN_DATED_SCORE = 0.5


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    fresh = [json.loads(line) for line in (DS_DIR / "fresh_150.jsonl").open()]
    fl = atlas.link_sources(fresh)
    top1 = sum(x["top"] == it["ruling_id"] for x, it in zip(fl, fresh, strict=True))
    inset = sum(it["ruling_id"] in x["candidates"] for x, it in zip(fl, fresh, strict=True))
    validation = {
        "set": "fresh_150 (true ruling known)",
        "items": len(fresh),
        "top1_correct": top1,
        "true_ruling_in_candidates": inset,
        "mean_candidates": round(sum(len(x["candidates"]) for x in fl) / len(fl), 2),
    }
    print(validation)
    test = [json.loads(line) for line in (DS_DIR / "atlas_test_200.jsonl").open()]
    links = atlas.link_sources(test)
    items = {}
    for x in links:
        dated = x["dates"] and x["score"] >= MIN_DATED_SCORE
        items[x["item_id"]] = {
            **x,
            "as_of": min(x["dates"]) if dated else None,
            "tier": None
            if not dated
            else ("unique" if len(x["candidates"]) == 1 else "earliest_of_candidates"),
        }
    out = {
        "note": "Source ruling candidates for ATLAS test items. as_of is the earliest candidate date when the top score is at least "
        f"{MIN_DATED_SCORE}.",
        "method": "atlas.link_sources",
        "validation": validation,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "items": items,
    }
    (DS_DIR / "source_links.json").write_text(json.dumps(out, indent=1))
    n_dated = sum(v["as_of"] is not None for v in items.values())
    print("atlas_test_200:", len(items), "items,", n_dated, "dated")
    if a.apply:
        con = connect()
        con.execute("DELETE FROM eval_redactions WHERE method = 'v2_overlap_code'")
        for iid, v in items.items():
            for rid in v["candidates"]:
                con.execute(
                    "INSERT OR REPLACE INTO eval_redactions VALUES (?,?,?,?,?)",
                    (rid, "atlas_test_200", iid, v["score"], "v2_overlap_code"),
                )
        con.commit()
        print(
            "redactions now:",
            con.execute("SELECT COUNT(DISTINCT ruling_id) FROM eval_redactions").fetchone()[0],
        )
    print(ROOT)


if __name__ == "__main__":
    main()
