"""Failure taxonomy.

Categories were set after reading baseline failures (see docs/EVAL.md, "Error
analysis"). The digit-level category is computed; the cause categories come from
manual tags written while reading traces (evals/taxonomy/<run_id>.jsonl).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tariffagent.config import ROOT

TAX_DIR = ROOT / "evals" / "taxonomy"

# Where the answer first diverged from the gold code.
LEVEL = {
    "wrong_chapter": "First 2 digits differ.",
    "wrong_heading": "Chapter right, 4-digit heading wrong.",
    "wrong_subheading": "Heading right, 6 or 8 digits wrong.",
    "wrong_stat_suffix": "8 digits right, statistical suffix wrong.",
    "no_answer": "No code returned (error or abstention with no guess).",
}

# Why it went wrong. One primary cause per failure, from reading the trace.
CAUSES = {
    "gri_misapplied": "Applied the wrong GRI or skipped one (for example used GRI 3(b) where a note decided under GRI 1).",
    "note_missed": "A section or chapter note or exclusion that decides the case was not read or not applied.",
    "fact_misread": "Misread or ignored a fact in the description (material, function, value, gender, construction).",
    "should_have_abstained": "The description lacks a fact that decides the code; the agent guessed with high confidence.",
    "stale_ruling_relied_on": "Relied on a revoked, modified or outdated-code ruling.",
    "hallucinated_citation": "Cited a ruling that does not exist in the corpus or was never retrieved.",
    "precedent_mismatch": "Followed a ruling on a different product or different facts.",
    "retrieval_miss": "The relevant heading or precedent never surfaced in tool results.",
    "gold_questionable": "The gold code is doubtful given the description (ambiguous description, or tariff changed since).",
    "budget_exhausted": "Ran out of turns or tokens before settling the code.",
    # Added after reading the dev100-A failures (2026-09-29):
    "stat_suffix_misnavigated": "Right 8 digits, but picked a statistical line with the same label under the wrong parent, or one from an older revision.",
    "abstained_missing_fact": "Abstained, correctly, because the description lacks a fact that decides the code (size, grade, power source).",
    "over_abstained": "Abstained although the description and precedent were enough to answer.",
    "malformed_output": "The final answer was not valid JSON (cut off at max_tokens or degenerate repetition).",
}


def level_of(row: dict) -> str | None:
    if not row.get("pred"):
        return "no_answer"
    depth = row["scored_depth"]
    if row.get(f"exact_{depth}"):
        return None
    if not row.get("exact_2"):
        return "wrong_chapter"
    if not row.get("exact_4"):
        return "wrong_heading"
    if depth >= 6 and not row.get("exact_6"):
        return "wrong_subheading"
    if depth >= 8 and not row.get("exact_8"):
        return "wrong_subheading"
    return "wrong_stat_suffix"


def load_tags(run_id: str) -> dict[str, dict]:
    p = TAX_DIR / f"{run_id}.jsonl"
    if not p.exists():
        return {}
    return {json.loads(line)["item_id"]: json.loads(line) for line in p.open() if line.strip()}


def distribution(scored: list[dict], tags: dict[str, dict]) -> dict:
    fails = [r for r in scored if level_of(r)]
    lv = Counter(level_of(r) for r in fails)
    causes = Counter(tags[r["item_id"]]["cause"] for r in fails if r["item_id"] in tags)
    return {
        "n_failures": len(fails),
        "n_tagged": sum(1 for r in fails if r["item_id"] in tags),
        "by_level": dict(lv.most_common()),
        "by_cause": dict(causes.most_common()),
    }


def write_tags(run_id: str, tags: list[dict]) -> Path:
    TAX_DIR.mkdir(parents=True, exist_ok=True)
    p = TAX_DIR / f"{run_id}.jsonl"
    with p.open("w") as f:
        for t in tags:
            assert t["cause"] in CAUSES, t
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return p
