"""Evaluation datasets with a manifest (source, date range, size, sha256, split).

- atlas_test_200: the published ATLAS test split, intact.
- dev_100: 100 items sampled (seed 13) from the ATLAS validation split. Prompt work only.
- fresh_N: CROSS rulings dated after the newest model training cutoff in use.
- subset_N: stratified subset of atlas_test_200 for the expensive arms and repeats.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import UTC, datetime
from pathlib import Path

from tariffagent.config import ROOT
from tariffagent.data import atlas
from tariffagent.data.crosswalk import Crosswalk

DS_DIR = ROOT / "evals" / "datasets"
MANIFEST = DS_DIR / "manifest.json"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_dataset(name: str, items: list[dict], meta: dict) -> dict:
    DS_DIR.mkdir(parents=True, exist_ok=True)
    p = DS_DIR / f"{name}.jsonl"
    with p.open("w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    man[name] = {
        **meta,
        "size": len(items),
        "sha256": _sha(p),
        "file": f"evals/datasets/{name}.jsonl",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    MANIFEST.write_text(json.dumps(man, indent=2, sort_keys=True))
    return man[name]


def load_dataset(name: str) -> list[dict]:
    p = DS_DIR / f"{name}.jsonl"
    man = json.loads(MANIFEST.read_text())
    if _sha(p) != man[name]["sha256"]:
        raise ValueError(f"{name} does not match its manifest sha256")
    return [json.loads(line) for line in p.open()]


def _with_crosswalk(items: list[dict], cw: Crosswalk) -> list[dict]:
    out = []
    for it in items:
        m = cw.map(it["gold_code"])
        it = dict(it)
        it["gold_current"] = m["current_code"]
        it["crosswalk_method"] = m["method"]
        it["code_stale"] = m["stale"]
        out.append(it)
    return out


def build_atlas() -> dict:
    cw = Crosswalk()
    test = _with_crosswalk(atlas.load("test"), cw)
    val = atlas.load("validation")
    rng = random.Random(13)
    idx = sorted(rng.sample(range(len(val)), 100))
    dev = _with_crosswalk([val[i] for i in idx], cw)
    src = "huggingface.co/datasets/Dayanand314Krishna/cross_rulings_hts_dataset_for_tariffs (mirror of flexifyai ATLAS)"
    return {
        "atlas_test_200": write_dataset(
            "atlas_test_200", test, {"source": src, "split": "test", "use": "reported results"}
        ),
        "dev_100": write_dataset(
            "dev_100",
            dev,
            {
                "source": src,
                "split": "validation (100 of 200, seed 13)",
                "use": "prompt work only, never reported",
            },
        ),
    }


def product_type(it: dict) -> str:
    """Rule-based stratum from the description and the reference reasoning."""
    d = it["description"].lower()
    r = (it.get("reference_reasoning") or "").lower()
    if re.search(r"\b(set|kit)s?\b", d) or "put up in sets" in r or "retail set" in r:
        return "sets"
    if re.search(r"\bpart(s)?\b|component|accessor|assembl(y|ies) for|replacement", d) or re.search(
        r"parts (and accessories )?of", r
    ):
        return "parts_accessories"
    if "essential character" in r or "composite" in r or "gri 3" in r or "gri 3" in d:
        return "composites"
    return "simple"


def plausible_headings(it: dict) -> int:
    """Distinct 4-digit headings named in the reference reasoning (gold plus alternatives CBP discussed)."""
    r = it.get("reference_reasoning") or ""
    heads = {m[:4] for m in re.findall(r"\b(\d{4})(?:\.\d{2})", r)} | {
        m for m in re.findall(r"heading (\d{4})\b", r)
    }
    heads.add(it["gold_digits"][:4])
    return len(heads)


def build_subset(n: int = 80, seed: int = 13) -> dict:
    """Stratified subset of atlas_test_200 in an order where any prefix stays balanced."""
    items = load_dataset("atlas_test_200")
    rng = random.Random(seed)
    strata: dict[str, list[dict]] = {}
    for it in items:
        it = dict(it)
        it["product_type"] = product_type(it)
        it["n_headings"] = plausible_headings(it)
        it["ambiguous"] = it["n_headings"] >= 2
        strata.setdefault(f"{it['product_type']}|{'multi' if it['ambiguous'] else 'single'}", []).append(it)
    for v in strata.values():
        rng.shuffle(v)
    order: list[dict] = []
    keys = sorted(strata)
    while len(order) < n and any(strata.values()):
        for k in keys:
            if strata[k] and len(order) < n:
                order.append(strata[k].pop())
    counts: dict[str, int] = {}
    for it in order:
        key = f"{it['product_type']}|{'multi' if it['ambiguous'] else 'single'}"
        counts[key] = counts.get(key, 0) + 1
    meta = {
        "source": "atlas_test_200",
        "split": f"stratified by product type and plausible headings, round-robin order, seed {seed}",
        "strata": counts,
        "use": "arms B and C and repeat runs",
    }
    return {f"subset_{len(order)}": write_dataset(f"subset_{len(order)}", order, meta)}
