"""Write a descriptions-only copy of a dataset for blind classification (no gold fields).

    uv run python scripts/blind_items.py atlas_test_200 --items-from subset_80 --out evals/blind/subset_80.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tariffagent.evals.datasets import load_dataset

ap = argparse.ArgumentParser()
ap.add_argument("dataset")
ap.add_argument("--items-from", default="")
ap.add_argument("--out", required=True)
a = ap.parse_args()
items = load_dataset(a.dataset)
if a.items_from:
    keep = {it["item_id"] for it in load_dataset(a.items_from)}
    items = [it for it in items if it["item_id"] in keep]
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w") as f:
    for it in items:
        f.write(json.dumps({"item_id": it["item_id"], "description": it["description"]}) + "\n")
print(f"wrote {len(items)} blind items to {out}")
