"""Check that every percentage and dollar figure in the public docs comes from evals/reports/.

Collects every number in evals/reports/*.json (and *.md), then scans the given docs for
figures written as `12.3%`, `12%` or `$0.0288`. A percentage matches a report value v when
v*100 (or v itself) rounds to the written figure; a dollar figure matches when v rounds
to it. Lines containing `audit:skip` are ignored (for example prices quoted from a
pricing page, which are not results).

    uv run python scripts/number_audit.py README.md docs/CASE_STUDY.md
Exit code 1 when a figure has no source.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "evals" / "reports"
PCT = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d+)?)\s?%")
USD = re.compile(r"\$(\d+(?:\.\d+)?)")


def report_values() -> list[float]:
    vals: list[float] = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, int | float):
            vals.append(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for p in REPORTS.glob("*.json"):
        walk(json.loads(p.read_text()))
    for p in REPORTS.glob("*.md"):
        vals += [float(m) for m in re.findall(r"\d+(?:\.\d+)?", p.read_text())]
    return vals


def decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def matches(written: str, vals: list[float], pct: bool) -> bool:
    w = float(written)
    d = decimals(written)
    tol = 0.5 * 10**-d + 1e-9
    for v in vals:
        cands = [v * 100, v] if pct else [v]
        if any(abs(c - w) <= tol for c in cands):
            return True
    return False


def audit(paths: list[str]) -> int:
    vals = report_values()
    bad = 0
    for path in paths:
        for i, line in enumerate(Path(path).read_text().splitlines(), 1):
            if "audit:skip" in line:
                continue
            for m in PCT.finditer(line):
                if not matches(m.group(1), vals, pct=True):
                    print(f"{path}:{i}: {m.group(0)} not found in evals/reports")
                    bad += 1
            for m in USD.finditer(line):
                if not matches(m.group(1), vals, pct=False):
                    print(f"{path}:{i}: ${m.group(1)} not found in evals/reports")
                    bad += 1
    print(f"number audit: {bad} unsourced figure(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(audit(sys.argv[1:] or ["README.md", "docs/CASE_STUDY.md"]))
