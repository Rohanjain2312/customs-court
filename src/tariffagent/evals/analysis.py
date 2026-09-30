"""Judge runs, judge validation, and arm comparisons with bootstrap CIs and slices."""

from __future__ import annotations

import json

from tariffagent.config import ROOT, get_settings
from tariffagent.evals.datasets import load_dataset, plausible_headings, product_type
from tariffagent.evals.judge import run_judge
from tariffagent.evals.run import REPORTS, load_run
from tariffagent.evals.stats import bootstrap_ci, cohen_kappa, paired_diff

LINKS = {
    "atlas_test_200": ROOT / "data" / "atlas_test_200_links.json",
    "subset_80": ROOT / "data" / "atlas_test_200_links.json",
}


def _links(dataset: str) -> dict:
    p = LINKS.get(dataset)
    if p and p.exists():
        return {x["item_id"]: x for x in json.loads(p.read_text())}
    return {}


def judge_and_validate(run_id: str, second_model: str | None = None, second: bool = True) -> dict:
    """Primary judge (cheap Claude model) plus a second judge from another vendor for kappa."""
    results, scored, report = load_run(run_id)
    items = load_dataset(report["dataset"])
    ids = {r["item_id"] for r in results}
    items = [it for it in items if it["item_id"] in ids]
    links = _links(report["dataset"])
    s = get_settings()
    j1 = run_judge(items, results, run_id=f"judge-{run_id}", model=s.judge_model, links=links, batch=True)
    out = {
        "run_id": run_id,
        "judge_model": s.judge_model,
        "n_judged": sum(v["verdict"] is not None for v in j1.values()),
    }
    by = {r["item_id"]: r for r in scored}
    passes = [v["verdict"] == "pass" for v in j1.values() if v["verdict"]]
    out["pass_rate"] = bootstrap_ci(passes)
    # Programmatic proxy: exact at 10 digits should mostly pass; wrong chapter should fail.
    c10 = [j1[i]["verdict"] == "pass" for i in j1 if j1[i]["verdict"] and by[i]["exact_10"]]
    w2 = [j1[i]["verdict"] == "fail" for i in j1 if j1[i]["verdict"] and by[i]["exact_2"] is False]
    out["proxy_pass_given_correct10"] = {
        "rate": round(sum(c10) / len(c10), 4) if c10 else None,
        "n": len(c10),
    }
    out["proxy_fail_given_wrong_chapter"] = {
        "rate": round(sum(w2) / len(w2), 4) if w2 else None,
        "n": len(w2),
    }
    out["reference_sources"] = {
        k: sum(1 for v in j1.values() if v["reference"].startswith(k)) for k in ("ruling", "atlas_reasoning")
    }
    if second and (second_model or s.openai_api_key):
        # batch=False: the second judge may be a provider without a batch API (runs in a thread pool).
        m2 = second_model or s.openai_model
        j2 = run_judge(items, results, run_id=f"judge2-{run_id}", model=m2, links=links, batch=False)
        both = [i for i in j1 if j1[i]["verdict"] and j2.get(i, {}).get("verdict")]
        a = [j1[i]["verdict"] == "pass" for i in both]
        b = [j2[i]["verdict"] == "pass" for i in both]
        out["second_judge_model"] = m2
        out["cohen_kappa"] = cohen_kappa(a, b)
        out["raw_agreement"] = (
            round(sum(x == y for x, y in zip(a, b, strict=True)) / len(both), 4) if both else None
        )
        out["n_both"] = len(both)
        out["second_pass_rate"] = round(sum(b) / len(b), 4) if b else None
    out["verdicts"] = {i: v["verdict"] for i, v in j1.items()}
    (REPORTS / f"{run_id}.judge.json").write_text(json.dumps(out, indent=2))
    return out


def compare(run_ids: dict[str, str], dataset: str, levels=(10, 8, 6, 4)) -> dict:
    """run_ids: arm label -> run id (same dataset). Paired bootstrap of every arm against the first."""
    items = {it["item_id"]: it for it in load_dataset(dataset)}
    runs = {}
    for label, rid in run_ids.items():
        _, scored, report = load_run(rid)
        runs[label] = {"scored": {r["item_id"]: r for r in scored}, "report": report}
    base = next(iter(run_ids))
    out: dict = {"dataset": dataset, "runs": run_ids, "arms": {}, "vs_" + base: {}}
    for label, r in runs.items():
        m = r["report"]["metrics"]
        out["arms"][label] = {
            **{
                f"acc_{k}": bootstrap_ci(
                    [x[f"exact_{k}"] for x in r["scored"].values() if x[f"exact_{k}"] is not None]
                )
                for k in levels
            },
            "usd_per_item": m["usd_per_item"],
            "tokens_per_item": m["tokens_per_item"],
            "latency_p50_s": m["latency_p50_s"],
            "latency_p95_s": m["latency_p95_s"],
            "cache_hit_rate": m["cache_hit_rate"],
            "mode": r["report"]["mode"],
        }
    for label, r in runs.items():
        if label == base:
            continue
        diffs = {}
        for k in levels:
            a = {
                i: float(x[f"exact_{k}"])
                for i, x in runs[base]["scored"].items()
                if x[f"exact_{k}"] is not None
            }
            b = {i: float(x[f"exact_{k}"]) for i, x in r["scored"].items() if x[f"exact_{k}"] is not None}
            diffs[f"acc_{k}"] = paired_diff(a, b)
        out["vs_" + base][label] = diffs
    # Slices: product type and number of plausible headings.
    slices: dict = {}
    for label, r in runs.items():
        for iid, x in r["scored"].items():
            it = items[iid]
            for sl in (
                f"type={product_type(it)}",
                f"headings={'2+' if plausible_headings(it) >= 2 else '1'}",
            ):
                slices.setdefault(sl, {}).setdefault(label, []).append(
                    x["exact_6"] if x["exact_6"] is not None else False
                )
    out["slices_acc6"] = {
        sl: {label: bootstrap_ci(v) for label, v in arms.items()} for sl, arms in sorted(slices.items())
    }
    return out
