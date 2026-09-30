"""How many citations in the runs made before the date filter were dated after the item's own ruling.

Writes evals/reports/as_of_impact.json. The filtered runs (`*-asof`) should show none.

    uv run python scripts/as_of_impact.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tariffagent.agents.tooling import item_as_of
from tariffagent.config import get_settings
from tariffagent.evals.datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    ("cc-subset80-A", "atlas_test_200", "subset_80", "no date filter"),
    ("cc-subset80-A-asof", "atlas_test_200", "subset_80", "date filter on"),
    ("cc-fresh40-A", "fresh_150", "fresh_40", "no date filter"),
    ("cc-fresh40-A-asof", "fresh_150", "fresh_40", "date filter on"),
]


def main() -> None:
    con = sqlite3.connect(f"file:{get_settings().db_path}?mode=ro", uri=True)
    out = {}
    for run, ds, sub, label in RUNS:
        keep = {it["item_id"] for it in load_dataset(sub)}
        items = {it["item_id"]: it for it in load_dataset(ds) if it["item_id"] in keep}
        dated = [i for i, it in items.items() if item_as_of(it)]
        late, late_items = [], set()
        for iid in dated:
            raw = json.loads((ROOT / "evals" / "blind" / "out" / run / f"{iid}.json").read_text())
            for c in raw["classification"].get("cited_rulings", []):
                r = con.execute("SELECT date FROM rulings WHERE id=?", (c["id"],)).fetchone()
                if r and r[0] and r[0] > item_as_of(items[iid]):
                    late.append({"item_id": iid, "cited": c["id"], "cited_date": r[0]})
                    late_items.add(iid)
        out[run] = {
            "filter": label,
            "items": len(items),
            "items_with_as_of_date": len(dated),
            "citations_dated_after_the_item": len(late),
            "items_citing_a_later_ruling": len(late_items),
            "detail": late,
        }
        print(run, label, len(dated), "dated;", len(late), "late citations in", len(late_items), "items")
    (ROOT / "evals" / "reports" / "as_of_impact.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
