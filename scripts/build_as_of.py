"""Write evals/datasets/as_of.json: the date after which rulings are hidden from the tools, per item.

An item's as-of date is the date of its own ruling, because a broker classifying that product could
not have had later precedent.
- fresh items carry their ruling's date (exact).
- ATLAS test items carry no date, so it comes from evals/datasets/source_links.json (built by
  scripts/build_source_links.py): the earliest date among the candidate source rulings, when the
  best candidate scores at least 0.5. Items below that have no cutoff rather than a wrong one.

    uv run python scripts/build_as_of.py
"""

from __future__ import annotations

import hashlib
import json

from tariffagent.config import ROOT

DS = ROOT / "evals" / "datasets"


def main() -> None:
    links = json.loads((DS / "source_links.json").read_text())["items"]
    items: dict[str, dict] = {}
    cov: dict[str, dict] = {}
    for name in ("atlas_test_200", "subset_80", "fresh_150", "fresh_40", "fresh_300"):
        p = DS / f"{name}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(line) for line in p.open()]
        tiers: dict[str, int] = {}
        for it in rows:
            iid = it["item_id"]
            if it.get("ruling_date"):
                items[iid] = {"as_of": it["ruling_date"], "basis": "ruling_date", "tier": "exact"}
            elif links.get(iid, {}).get("as_of"):
                v = links[iid]
                items[iid] = {
                    "as_of": v["as_of"],
                    "basis": f"earliest of candidate source rulings {','.join(v['candidates'])} (score {v['score']})",
                    "tier": v["tier"],
                }
            if iid in items:
                tiers[items[iid]["tier"]] = tiers.get(items[iid]["tier"], 0) + 1
        cov[name] = {"items": len(rows), "with_as_of": sum(tiers.values()), "by_tier": tiers}
    out = {
        "note": "Rulings dated after an item's as_of are hidden from the tools during evaluation.",
        "coverage": cov,
        "items": dict(sorted(items.items())),
    }
    text = json.dumps(out, indent=1)
    (DS / "as_of.json").write_text(text)
    print(json.dumps(cov, indent=1), hashlib.sha256(text.encode()).hexdigest()[:12])


if __name__ == "__main__":
    main()
