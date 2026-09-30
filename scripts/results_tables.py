"""Build every results table in the docs from evals/reports and evals/runs. Offline, no spend.

Writes evals/reports/summary_tables.json (all numbers, so the number audit can trace them)
and replaces the text between `<!-- results:NAME -->` and `<!-- /results:NAME -->` markers
in README.md, docs/CASE_STUDY.md and docs/EVAL.md.

    uv run python scripts/results_tables.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tariffagent.evals.datasets import load_dataset
from tariffagent.evals.stats import bootstrap_ci, paired_diff

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "evals" / "reports"
RUNS = ROOT / "evals" / "runs"
DOCS = [ROOT / "README.md", ROOT / "docs" / "CASE_STUDY.md", ROOT / "docs" / "EVAL.md", ROOT / "docs" / "BLOG.md"]

SONNET = "Claude Sonnet 5"
OPUS_CC = "Claude Opus 5.5"


def scored(run_id: str) -> dict[str, dict] | None:
    p = RUNS / run_id / "scored.jsonl"
    if not p.exists():
        return None
    return {r["item_id"]: r for r in (json.loads(x) for x in p.open())}


def report(run_id: str) -> dict | None:
    p = REP / f"{run_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def stats(run_id: str, ids: set[str] | None = None) -> dict | None:
    rows = scored(run_id)
    rep = report(run_id)
    if rows is None or rep is None:
        return None
    if ids is not None:
        rows = {k: v for k, v in rows.items() if k in ids}
    rs = list(rows.values())
    out = {"run_id": run_id, "n": len(rs)}
    for k in (10, 8, 6, 4):
        vals = [r[f"exact_{k}"] for r in rs if r[f"exact_{k}"] is not None]
        out[f"acc_{k}"] = bootstrap_ci(vals)
    out["abstain_rate"] = round(sum(r["abstain"] for r in rs) / max(1, len(rs)), 4)
    ans = [r for r in rs if not r["abstain"] and r["pred"]]
    out["acc6_when_answering"] = round(sum(bool(r["exact_6"]) for r in ans) / len(ans), 4) if ans else None
    out["usd_per_item"] = round(sum(r["usd"] for r in rs) / max(1, len(rs)), 5)
    out["tokens_per_item"] = round(sum(r["tokens"] for r in rs) / max(1, len(rs)), 1)
    out["tool_calls_per_item"] = round(sum(r["tool_calls"] for r in rs) / max(1, len(rs)), 2)
    out["mode"] = rep.get("mode")
    out["models"] = rep.get("models")
    return out


def pct(ci: dict | None) -> str:
    if not ci or ci.get("mean") is None:
        return "n/a"
    return f"{ci['mean'] * 100:.1f}% [{ci['lo'] * 100:.1f}, {ci['hi'] * 100:.1f}]"


def usd(x) -> str:
    return "n/a" if x is None else ("$0" if x == 0 else f"${x:.4f}")


def row(label: str, model: str, s: dict | None, cost_note: str = "") -> str:
    if s is None:
        return f"| {label} | {model} | not run yet | | | | |"
    return (
        f"| {label} | {model} | {pct(s['acc_10'])} | {pct(s['acc_6'])} | {pct(s['acc_4'])} | "
        f"{s['abstain_rate'] * 100:.1f}% | {usd(s['usd_per_item'])}{cost_note} |"
    )


HEAD = "| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |\n|---|---|---|---|---|---|---|"


def build() -> tuple[dict, dict[str, str]]:
    data: dict = {}
    tables: dict[str, str] = {}
    pub = json.loads((REP / "atlas_published.json").read_text())["models"]

    # Headline: atlas_test_200 (full 200)
    h = {k: stats(k) for k in ("atlas200-Z",)}
    data["atlas200"] = h
    tables["headline"] = "\n".join(
        [
            HEAD,
            f"| ATLAS fine-tuned LLaMA-3.3-70B (published) | paper | {pub['atlas_llama_3.3_70b_finetuned']['exact_10'] * 100:.1f}% | {pub['atlas_llama_3.3_70b_finetuned']['exact_6'] * 100:.1f}% | | | |",
            f"| GPT-5-Thinking (published in ATLAS) | paper | {pub['gpt_5_thinking']['exact_10'] * 100:.1f}% | | | | |",
            f"| Gemini-2.5-Pro-Thinking (published in ATLAS) | paper | {pub['gemini_2.5_pro_thinking']['exact_10'] * 100:.1f}% | | | | |",
            row("Zero-shot, no tools, all 200", SONNET, h["atlas200-Z"]),
        ]
    )

    # Agent results on subset_80 (stratified 80 of the 200 test items); every row on the same items.
    ids = {it["item_id"] for it in load_dataset("subset_80")}
    sub = {
        "Z": stats("atlas200-Z", ids),
        "O": stats("subset80-O"),
        "A_cc": stats("cc-subset80-A"),
    }
    data["subset80"] = sub
    tables["subset"] = "\n".join(
        [
            HEAD,
            row("Zero-shot, no tools", SONNET, sub["Z"]),
            row("TariffAgent single agent (API)", "gpt-5-mini", sub["O"]),
            row("TariffAgent single agent (in the Claude Code session)", OPUS_CC, sub["A_cc"], " (no API spend)"),
        ]
    )
    diffs = {}
    base = scored("cc-subset80-A")
    for arm, rid in (("Z", "atlas200-Z"), ("O", "subset80-O")):
        other = scored(rid)
        if base and other:
            for k in (10, 6):
                a = {i: float(other[i][f"exact_{k}"]) for i in ids if i in other and other[i][f"exact_{k}"] is not None}
                b = {i: float(base[i][f"exact_{k}"]) for i in ids if i in base and base[i][f"exact_{k}"] is not None}
                diffs[f"A_cc_minus_{arm}_acc{k}"] = paired_diff(a, b)
    data["subset80_diffs"] = diffs

    def dline(key):
        d = diffs.get(key)
        if not d or d.get("diff") is None:
            return "n/a"
        return f"{d['diff'] * 100:+.1f} points [{d['lo'] * 100:+.1f}, {d['hi'] * 100:+.1f}], n={d['n']}"

    tables["subset_diffs"] = "\n".join(
        [
            "| Comparison (paired, same items) | 10-digit | 6-digit |",
            "|---|---|---|",
            f"| Agent (Claude in session) minus Claude Sonnet 5 zero-shot | {dline('A_cc_minus_Z_acc10')} | {dline('A_cc_minus_Z_acc6')} |",
            f"| Agent (Claude in session) minus agent on gpt-5-mini | {dline('A_cc_minus_O_acc10')} | {dline('A_cc_minus_O_acc6')} |",
        ]
    )

    # Fresh set
    f = {k: stats(k) for k in ("fresh150-Z",)}
    data["fresh150"] = f
    tables["fresh"] = "\n".join([HEAD, row("Zero-shot, no tools", SONNET, f["fresh150-Z"])])

    # Claude agent runs on dev (prompt work only, not a reported test result)
    dv = {k: stats(k) for k in ("dev100-A", "dev40-A-v1", "dev10-D-v2", "pilot-dev20-A")}
    data["dev"] = dv
    tables["dev"] = "\n".join(
        [
            HEAD,
            row("Single agent, prompt v0 (dev_100)", SONNET, dv["dev100-A"]),
            row("Single agent, prompt v1.2 (first 40 of dev_100)", SONNET, dv["dev40-A-v1"]),
            row("Multi-agent (first 10 of dev_100)", "Claude Haiku 4.5 + Claude Sonnet 5", dv["dev10-D-v2"]),
            row("Pilot (first 20 of dev_100)", "Claude Sonnet 5.5", dv["pilot-dev20-A"]),
        ]
    )

    cost = json.loads((REP / "cost_summary.json").read_text())["total"]
    data["cost"] = cost
    tables["cost"] = "\n".join(
        [
            "| | USD |",
            "|---|---|",
            f"| Paid API spend, whole project | ${cost['actual_usd']:.2f} |",
            f"| Same calls at list price, no caching, no batch discount | ${cost['no_cache_no_batch_usd']:.2f} |",
            f"| Saving from prompt caching and the Batch API | {cost['saving_vs_no_cache_no_batch'] * 100:.1f}% |",
            f"| Share of input tokens read from the prompt cache | {cost['cache_read_share'] * 100:.1f}% |",
            "| Open-weights runs (HF Job, included PRO credits) | $0 extra |",
        ]
    )
    return data, tables


def main() -> None:
    data, tables = build()
    (REP / "summary_tables.json").write_text(json.dumps(data, indent=2))
    for doc in DOCS:
        if not doc.exists():
            continue
        text = doc.read_text()
        for name, body in tables.items():
            text = re.sub(
                rf"(<!-- results:{name} -->).*?(<!-- /results:{name} -->)",
                lambda m, b=body: m.group(1) + "\n" + b + "\n" + m.group(2),
                text,
                flags=re.S,
            )
        doc.write_text(text)
    print(
        "wrote evals/reports/summary_tables.json and refreshed tables in",
        [d.name for d in DOCS if d.exists()],
    )
    for name, body in tables.items():
        print(f"\n## {name}\n{body}")


if __name__ == "__main__":
    main()
