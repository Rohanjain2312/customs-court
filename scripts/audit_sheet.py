"""Write evals/audit/audit_25.md: an optional 25-case spot-check sheet for the reasoning judge.

Takes every case where the two judges disagree, then fills to 25 with a seeded random
sample of the rest. Each case shows the product, the agent's code and reasoning, the
gold code, both verdicts and a blank line for a human verdict. Never blocks anything.

    uv run python scripts/audit_sheet.py cc-subset80-A
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JDIR = ROOT / "evals" / "blind" / "judge"
RUNS = ROOT / "evals" / "runs"
OUT = ROOT / "evals" / "audit" / "audit_25.md"


def lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def verdicts(run_id: str, judge: str) -> dict[str, dict]:
    d = JDIR / run_id
    files = [d / f"verdicts_{judge}.jsonl"]
    if not files[0].exists():
        files = sorted(d.glob(f"verdicts_{judge}_[0-9][0-9].jsonl"))
    return {v["item_id"]: v for f in files for v in lines(f)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    packets = {p["item_id"]: p for p in lines(JDIR / a.run_id / "packets.jsonl")}
    scored = {r["item_id"]: r for r in lines(RUNS / a.run_id / "scored.jsonl")}
    j1, j2 = verdicts(a.run_id, "opus"), verdicts(a.run_id, "haiku")
    ids = sorted(i for i in packets if i in j1 and i in j2)
    split = sorted(i for i in ids if j1[i]["verdict"] != j2[i]["verdict"])
    rest = [i for i in ids if i not in split]
    random.Random(a.seed).shuffle(rest)
    pick = sorted(split + rest[: max(0, a.n - len(split))])[: a.n]
    out = [
        "# Judge spot-check sheet (optional)",
        "",
        f"Run `{a.run_id}`. {len(pick)} cases: all {len(split)} where the two judges disagree, "
        f"then a random fill (seed {a.seed}). Judge 1 is Claude Opus 5.5, judge 2 is Claude Haiku 4.5, "
        "both in the Claude Code session. The question for each case: did the agent reach CBP's heading "
        "for the same legal reason? Write pass or fail on the last line. Nothing depends on this sheet.",
        "",
    ]
    for n, i in enumerate(pick, 1):
        p, s, ans = packets[i], scored.get(i, {}), packets[i]["assistant_answer"]
        out += [
            f"## {n}. {i}" + ("  (judges disagree)" if i in split else ""),
            "",
            f"**Product.** {p['product'][:600]}",
            "",
            f"**Gold code.** {s.get('gold', '')}. **Agent code.** {ans['hts10']} "
            f"(deciding rule: {ans.get('deciding_gri', '')}).",
            "",
            f"**Agent reasoning.** {ans.get('rationale', '')}",
            "",
            f"**CBP reference.** `{p['reference_source']}`, in `evals/blind/judge/{a.run_id}/packets.jsonl`.",
            "",
            f"- Judge 1: {j1[i]['verdict']}. {j1[i].get('reason', '')}",
            f"- Judge 2: {j2[i]['verdict']}. {j2[i].get('reason', '')}",
            "- Your verdict: ____",
            "",
        ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out))
    print(f"wrote {OUT} ({len(pick)} cases, {len(split)} disagreements)")


if __name__ == "__main__":
    main()
