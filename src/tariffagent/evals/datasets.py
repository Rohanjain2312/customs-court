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
