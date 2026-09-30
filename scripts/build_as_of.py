"""Write evals/datasets/as_of.json: the date after which rulings are hidden from the tools, per item.

An item's as-of date is the date of its own ruling, because a broker classifying that product could
not have had later precedent.
- fresh items carry their ruling's date (exact).
- ATLAS items carry no date, so it comes from the linked source ruling (data/atlas_*_links.json,
  built by `tariffagent data`), and only when the link is confident (score >= MIN_SCORE).
  Less confident items get no cutoff, rather than a wrong one.

    uv run python scripts/build_as_of.py
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from tariffagent.config import ROOT, get_settings

DS = ROOT / "evals" / "datasets"
MIN_SCORE = 0.6
LINKS = {"atlas_test_200": "atlas_test_200_links.json", "dev_100": "atlas_validation_200_links.json"}


def main() -> None:
    con = sqlite3.connect(f"file:{get_settings().db_path}?mode=ro", uri=True)
    items: dict[str, dict] = {}
    cov: dict[str, dict] = {}
    for name in ("atlas_test_200", "dev_100", "subset_80", "fresh_150", "fresh_40", "fresh_300"):
        p = DS / f"{name}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(line) for line in p.open()]
        links = {}
        src = LINKS.get(name) or ("atlas_test_200_links.json" if name == "subset_80" else None)
        if src:
            links = {x["item_id"]: x for x in json.load(open(get_settings().data_dir / src))}
        n = 0
        for it in rows:
            iid = it["item_id"]
            if it.get("ruling_date"):
                items[iid] = {"as_of": it["ruling_date"], "basis": "ruling_date"}
            elif iid in links and links[iid]["ruling_id"] and links[iid]["score"] >= MIN_SCORE:
                d = con.execute("SELECT date FROM rulings WHERE id=?", (links[iid]["ruling_id"],)).fetchone()
                if d and d[0]:
                    items[iid] = {
                        "as_of": d[0],
                        "basis": f"linked ruling {links[iid]['ruling_id']} (score {links[iid]['score']})",
                    }
            n += iid in items
        cov[name] = {"items": len(rows), "with_as_of": n}
    out = {
        "note": "Rulings dated after an item's as_of are hidden from the tools during evaluation.",
        "min_link_score": MIN_SCORE,
        "coverage": cov,
        "items": dict(sorted(items.items())),
    }
    text = json.dumps(out, indent=1, sort_keys=False)
    (DS / "as_of.json").write_text(text)
    print(json.dumps(cov, indent=1), hashlib.sha256(text.encode()).hexdigest()[:12])


if __name__ == "__main__":
    main()
