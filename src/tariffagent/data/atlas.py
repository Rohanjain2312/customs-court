"""ATLAS benchmark data (arXiv 2509.18400).

The official repo flexifyai/cross_rulings_hts_dataset_for_tariffs returned
"Repository not found" on 2026-09-28. We use the public mirror
Dayanand314Krishna/cross_rulings_hts_dataset_for_tariffs, whose README is the
Flexify.AI card and whose split sizes match the paper (18,254 / 200 / 200).
The test split is kept intact.

ATLAS items carry no ruling ids, so link_to_rulings() finds the source ruling
in our corpus (same 10-digit code, highest text overlap). The links drive
--redact-eval so the agent cannot retrieve the golden ruling.

link_sources() is the second, stronger linker. It looks at the whole corpus, not only
rulings that list the gold code, because the gold code in ATLAS is sometimes wrong or
out of date (the first linker missed the source ruling for about one item in eight).
It is validated on the fresh set, where the true ruling is known.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from tariffagent.config import get_settings
from tariffagent.data.db import connect
from tariffagent.data.http import PoliteClient

MIRROR = (
    "https://huggingface.co/datasets/Dayanand314Krishna/cross_rulings_hts_dataset_for_tariffs/resolve/main"
)
SPLITS = {"train": "train.jsonl", "validation": "validation.jsonl", "test": "test.jsonl"}

Q_RE = re.compile(r"^What is the HTS US Code for (.*?)\??$", re.S)
A_RE = re.compile(r"HTS US Code\s*->\s*([0-9.]+)(?:\s*Reasoning\s*->\s*(.*))?", re.S)


def raw_dir() -> Path:
    return get_settings().data_dir / "raw" / "atlas"


def download() -> dict:
    http = PoliteClient(raw_dir(), min_interval_s=0)
    out = {}
    for split, fname in SPLITS.items():
        b = http.get_bytes(f"{MIRROR}/{fname}", fname)
        out[split] = hashlib.sha256(b).hexdigest()
    http.get_bytes(f"{MIRROR}/README.md", "README.md")
    return out


def parse_item(obj: dict, split: str, i: int) -> dict:
    msgs = obj["messages"]
    q = next(m["content"] for m in msgs if m["role"] == "user").strip()
    a = next(m["content"] for m in msgs if m["role"] == "assistant").strip()
    mq = Q_RE.match(q)
    desc = mq.group(1).strip() if mq else q
    ma = A_RE.search(a)
    code = ma.group(1).strip().rstrip(".") if ma else ""
    reasoning = (ma.group(2) or "").strip() if ma else ""
    return {
        "item_id": f"atlas_{split}_{i:05d}",
        "split": split,
        "description": desc,
        "gold_code": code,
        "gold_digits": re.sub(r"\D", "", code),
        "reference_reasoning": reasoning,
    }


def load(split: str) -> list[dict]:
    p = raw_dir() / SPLITS[split]
    if not p.exists():
        download()
    with p.open() as f:
        return [parse_item(json.loads(line), split, i) for i, line in enumerate(f) if line.strip()]


_TOK = re.compile(r"[a-z][a-z0-9\-]{2,}")
_STOP = set(
    "the and for with that this are from which was were has have its not all any but other than into such"
    " being been will would under heading subheading hts htsus classification classified tariff ruling"
    " product provides provided duty rate percent valorem item items".split()
)


def _toks(s: str) -> list[str]:
    return [t for t in _TOK.findall(s.lower()) if t not in _STOP]


def link_to_rulings(items: list[dict], dataset: str) -> list[dict]:
    """Link each item to the most likely source ruling and store redaction rows.

    Candidates are all rulings (CROSS metadata, with or without text) that list the
    gold 10-digit code (8 digits when 10 finds nothing). The score is IDF-weighted
    overlap between the item description and the ruling subject plus the first
    2,000 characters of text when we have it. The top match and near ties are
    redacted, so the agent cannot retrieve the golden ruling in --redact-eval mode.
    """
    con = connect()
    by_code: dict[str, list[str]] = {}
    for r in con.execute("SELECT id, tariffs FROM rulings"):
        for t in json.loads(r["tariffs"] or "[]"):
            d = re.sub(r"\D", "", t)
            if len(d) >= 8:
                by_code.setdefault(d[:10], []).append(r["id"])
                if len(d) > 8:
                    by_code.setdefault(d[:8], []).append(r["id"])
    df: Counter = Counter()
    docs: dict[str, set[str]] = {}
    n_docs = 0
    for r in con.execute("SELECT id, subject, substr(text, 1, 2000) t FROM rulings"):
        toks = set(_toks((r["subject"] or "") + " " + (r["t"] or "")))
        docs[r["id"]] = toks
        df.update(toks)
        n_docs += 1
    out = []
    for it in items:
        d = it["gold_digits"]
        cands = list(dict.fromkeys(by_code.get(d, []) or by_code.get(d[:8], [])))
        q = set(_toks(it["description"]))
        norm = sum(math.log(1 + n_docs / (1 + df[t])) for t in q) or 1.0
        scored = sorted(
            (
                (sum(math.log(1 + n_docs / (1 + df[t])) for t in q & docs.get(cid, set())) / norm, cid)
                for cid in cands
            ),
            reverse=True,
        )
        top = scored[0] if scored else (0.0, None)
        second = scored[1][0] if len(scored) > 1 else 0.0
        redact = [cid for sc, cid in scored if top[1] and sc >= 0.85 * top[0] and sc >= 0.2][:5]
        link = {
            "item_id": it["item_id"],
            "ruling_id": top[1],
            "score": round(top[0], 3),
            "margin": round(top[0] - second, 3),
            "n_candidates": len(scored),
            "redacted": redact,
        }
        for cid in redact:
            con.execute(
                "INSERT OR REPLACE INTO eval_redactions VALUES (?,?,?,?,?)",
                (cid, dataset, it["item_id"], link["score"], "code+idf_overlap_subject"),
            )
        out.append(link)
    con.commit()
    return out


def link_sources(
    items: list[dict], k: int = 25, tie: float = 0.85, floor: float = 0.35, cap: int = 8
) -> list[dict]:
    """Find each item's source ruling in the whole corpus.

    Candidates: the top `k` BM25 hits for the description, plus every ruling that lists the gold
    code (10 digits, else 8). Score: IDF-weighted share of the description's words found in the
    ruling's subject and first 2,000 characters, plus a bonus when the ruling lists the gold code
    (0.30 for 10 digits, 0.22 for 8, 0.12 for 6). `tie` is every candidate within 85% of the top
    score (and at least `floor`), at most `cap`. Several near-identical rulings on the same product
    often exist, so all of them are treated as possible sources: redact all, and date the item
    by the earliest (nothing later than any candidate can be precedent).
    """
    from tariffagent.index.search import HybridSearch

    con = connect(readonly=True)
    hs = HybridSearch(con, use_vectors=False)
    df: Counter = Counter()
    n = 0
    by_code: dict[str, list[str]] = {}
    for r in con.execute("SELECT id, subject, substr(text, 1, 2000) t, tariffs FROM rulings"):
        df.update(set(_toks((r["subject"] or "") + " " + (r["t"] or ""))))
        n += 1
        for t in json.loads(r["tariffs"] or "[]"):
            d = re.sub(r"\D", "", t)
            if len(d) >= 8:
                by_code.setdefault(d[:10], []).append(r["id"])
                if len(d) > 8:
                    by_code.setdefault(d[:8], []).append(r["id"])

    def idf(t: str) -> float:
        return math.log(1 + n / (1 + df[t]))

    out = []
    for it in items:
        g = it["gold_digits"]
        q = set(_toks(it["description"]))
        norm = sum(idf(t) for t in q) or 1.0
        pool = list(
            dict.fromkeys(
                [h.key for h in hs.search_rulings(it["description"], k=k)]
                + (by_code.get(g[:10]) or by_code.get(g[:8]) or [])
            )
        )
        scored = []
        for rid in pool:
            r = con.execute(
                "SELECT date, subject, tariffs, substr(text, 1, 2000) t FROM rulings WHERE id=?", (rid,)
            ).fetchone()
            ov = sum(idf(t) for t in q & set(_toks((r["subject"] or "") + " " + (r["t"] or "")))) / norm
            codes = [re.sub(r"\D", "", c) for c in json.loads(r["tariffs"] or "[]")]
            bonus = (
                0.30
                if any(c[:10] == g[:10] for c in codes)
                else 0.22
                if any(c[:8] == g[:8] for c in codes)
                else 0.12
                if any(c[:6] == g[:6] for c in codes)
                else 0.0
            )
            scored.append((ov + bonus, rid, r["date"] or ""))
        scored.sort(key=lambda x: (-x[0], x[1]))
        top = scored[0][0] if scored else 0.0
        ties = [x for x in scored if x[0] >= max(tie * top, floor)][:cap]
        dates = [d for _, _, d in ties if d]
        out.append(
            {
                "item_id": it["item_id"],
                "top": scored[0][1] if scored else None,
                "score": round(top, 3),
                "candidates": [rid for _, rid, _ in ties],
                "dates": dates,
            }
        )
    return out
