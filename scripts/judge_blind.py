"""Reasoning judge for runs, done in the Claude Code session (no API spend).

prepare: write one judge packet per item (product, CBP reference analysis, the agent's
         answer) using the same reference and prompt as evals/judge.py.
collect: read the verdict files of two judges, validate them the same way as
         evals/analysis.py (programmatic proxy and Cohen's kappa), and write
         evals/reports/<run_id>.judge.json.

    uv run python scripts/judge_blind.py prepare cc-subset80-A
    uv run python scripts/judge_blind.py collect cc-subset80-A --judge1 opus --judge2 haiku
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tariffagent.evals.analysis import _links
from tariffagent.evals.datasets import load_dataset
from tariffagent.evals.judge import JUDGE_SYSTEM, reference_for
from tariffagent.evals.run import REPORTS, load_run
from tariffagent.evals.stats import bootstrap_ci, cohen_kappa

ROOT = Path(__file__).resolve().parents[1]
JDIR = ROOT / "evals" / "blind" / "judge"
MODEL_IDS = {"opus": "claude-opus-5-5", "haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5-5"}


def prepare(run_id: str) -> None:
    results, _, report = load_run(run_id)
    items = {it["item_id"]: it for it in load_dataset(report["dataset"])}
    links = _links(report["dataset"])
    out = JDIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with (out / "packets.jsonl").open("w") as f:
        for r in results:
            cls = r.get("classification")
            if not cls or not cls.get("hts10"):
                continue
            it = items[r["item_id"]]
            ref, src = reference_for(it, links)
            if not ref:
                continue
            agent = {
                k: cls.get(k)
                for k in ("hts10", "deciding_gri", "gri_path", "rationale", "rejected_alternatives")
            }
            f.write(
                json.dumps(
                    {
                        "item_id": r["item_id"],
                        "reference_source": src,
                        "product": it["description"],
                        "cbp_reference": ref,
                        "assistant_answer": agent,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n += 1
    (out / "JUDGE_INSTRUCTIONS.md").write_text(JUDGE_SYSTEM + "\n")
    print(f"wrote {n} packets to {out}")


def _lines(run_id: str, judge: str) -> list[dict]:
    """Verdicts from verdicts_<judge>.jsonl, or from chunked verdicts_<judge>_NN.jsonl files."""
    d = JDIR / run_id
    files = [d / f"verdicts_{judge}.jsonl"]
    if not files[0].exists():
        files = sorted(d.glob(f"verdicts_{judge}_[0-9][0-9].jsonl"))
    return [json.loads(x) for f in files for x in f.read_text().splitlines() if x.strip()]


def _verdicts(run_id: str, judge: str) -> dict[str, str]:
    out = {}
    for v in _lines(run_id, judge):
        if v.get("verdict") in ("pass", "fail"):
            out[v["item_id"]] = v["verdict"]
    return out


def collect(run_id: str, judge1: str, judge2: str) -> None:
    _, scored, _ = load_run(run_id)
    by = {r["item_id"]: r for r in scored}
    packets = [json.loads(x) for x in (JDIR / run_id / "packets.jsonl").read_text().splitlines() if x.strip()]
    src = {p["item_id"]: p["reference_source"] for p in packets}
    j1, j2 = _verdicts(run_id, judge1), _verdicts(run_id, judge2)
    c10 = [j1[i] == "pass" for i in j1 if by[i]["exact_10"]]
    w2 = [j1[i] == "fail" for i in j1 if by[i]["exact_2"] is False]
    both = [i for i in j1 if i in j2]
    a = [j1[i] == "pass" for i in both]
    b = [j2[i] == "pass" for i in both]
    out = {
        "run_id": run_id,
        "mode": "judged in the Claude Code session (no API spend)",
        "judge_model": f"{MODEL_IDS.get(judge1, judge1)} (in session)",
        "second_judge_model": f"{MODEL_IDS.get(judge2, judge2)} (in session)",
        "graded_in_main_session": {
            j: sorted(v["item_id"] for v in _lines(run_id, j) if v.get("graded_by")) for j in (judge1, judge2)
        },
        "discarded_attempts": sorted(p.name for p in (JDIR / run_id).glob("discarded_*")),
        "prompt": "evals/judge.py JUDGE_SYSTEM, reference from evals/judge.py reference_for",
        "n_packets": len(packets),
        "n_judged": len(j1),
        "pass_rate": bootstrap_ci([v == "pass" for v in j1.values()]),
        "proxy_pass_given_correct10": {"rate": round(sum(c10) / len(c10), 4) if c10 else None, "n": len(c10)},
        "proxy_fail_given_wrong_chapter": {"rate": round(sum(w2) / len(w2), 4) if w2 else None, "n": len(w2)},
        "reference_sources": {
            k: sum(1 for i in j1 if src.get(i, "").startswith(k)) for k in ("ruling", "atlas_reasoning")
        },
        "cohen_kappa": cohen_kappa(a, b),
        "raw_agreement": round(sum(x == y for x, y in zip(a, b, strict=True)) / len(both), 4)
        if both
        else None,
        "n_both": len(both),
        "second_pass_rate": round(sum(b) / len(b), 4) if b else None,
        "verdicts": j1,
    }
    (REPORTS / f"{run_id}.judge.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "verdicts"}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "collect"])
    ap.add_argument("run_id")
    ap.add_argument("--judge1", default="opus")
    ap.add_argument("--judge2", default="haiku")
    a = ap.parse_args()
    prepare(a.run_id) if a.cmd == "prepare" else collect(a.run_id, a.judge1, a.judge2)
