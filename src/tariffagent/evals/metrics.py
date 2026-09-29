"""Scoring for one run: digit-level accuracy, citations, abstention, calibration, cost."""

from __future__ import annotations

import json
import re
from statistics import median

from tariffagent.data.db import connect

LEVELS = (10, 8, 6, 4, 2)


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def gold_targets(item: dict) -> tuple[list[str], int]:
    """Acceptable gold digit strings and the deepest level we can score at.

    exact / desc_match / single_child: 10 digits (the crosswalked current code and
    the original are both accepted). 8-digit golds: 8. Stale codes: 6.
    """
    g = item["gold_digits"]
    method = item.get("crosswalk_method", "exact")
    cur = digits(item.get("gold_current"))
    if item.get("code_stale"):
        return [g], 6
    if method in ("exact_8",) or len(g) == 8:
        return [g], 8
    targets = [g] + ([cur] if cur and cur != g else [])
    return targets, 10


def score_item(item: dict, pred_code: str | None) -> dict:
    p = digits(pred_code)
    targets, depth = gold_targets(item)
    out = {"scored_depth": depth, "pred_digits": p}
    for k in LEVELS:
        if k > depth:
            out[f"exact_{k}"] = None
        else:
            out[f"exact_{k}"] = bool(p) and any(p[:k] == t[:k] and len(p) >= k for t in targets)
    return out


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[i]


def ece(conf: list[float], correct: list[bool], bins: int = 10) -> float | None:
    if not conf:
        return None
    total = len(conf)
    err = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(conf) if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if not idx:
            continue
        acc = sum(correct[i] for i in idx) / len(idx)
        avg = sum(conf[i] for i in idx) / len(idx)
        err += len(idx) / total * abs(acc - avg)
    return round(err, 4)


def seen_ruling_ids(events: list[dict]) -> set[str]:
    ids: set[str] = set()
    for e in events:
        if e.get("type") == "tool_call":
            ids.update(re.findall(r"\b([A-Z]?\d{5,6})\b", e.get("result_preview", "")))
            ids.update(re.findall(r"\b([A-Z]?\d{5,6})\b", json.dumps(e.get("args", {}))))
    return ids


def citation_checks(cls: dict | None, events: list[dict], con) -> dict:
    """Each cited ruling: exists in corpus? status per our derivation? plausibly seen in a tool call?"""
    if not cls:
        return {"n_cited": 0, "valid": 0, "hallucinated": 0, "not_in_force": 0, "mislabeled_status": 0}
    n = valid = halluc = nif = mis = 0
    for c in cls.get("cited_rulings", []):
        rid = re.sub(r"^(NY|HQ)\s*", "", (c.get("id") or "").upper()).replace(" ", "")
        n += 1
        row = con.execute("SELECT status FROM ruling_status WHERE id=?", (rid,)).fetchone()
        if not row:
            halluc += 1
            continue
        if row["status"] == "in_force":
            valid += 1
        else:
            nif += 1
        if c.get("status") != row["status"]:
            mis += 1
    return {
        "n_cited": n,
        "valid": valid,
        "hallucinated": halluc,
        "not_in_force": nif,
        "mislabeled_status": mis,
    }


def score_run(items: list[dict], results: list[dict], with_citations: bool = True) -> tuple[list[dict], dict]:
    """Returns per-item rows and aggregate metrics. Citation checks need the full database."""
    con = connect(readonly=True) if with_citations else None
    by_id = {r["item_id"]: r for r in results}
    rows = []
    for it in items:
        r = by_id.get(it["item_id"], {"error": "missing"})
        cls = r.get("classification") or {}
        pred = cls.get("hts10") or ""
        row = {
            "item_id": it["item_id"],
            "gold": it["gold_code"],
            "pred": pred,
            "stale": bool(it.get("code_stale")),
            "abstain": bool(cls.get("abstain")),
            "confidence": cls.get("confidence"),
            "error": r.get("error") or r.get("parse_error") or "",
            "usd": r.get("usd", 0.0),
            "tokens": r.get("tokens", 0),
            "api_latency_s": r.get("api_latency_s"),
            "wall_s": r.get("wall_s"),
            "tool_calls": r.get("tool_calls", 0),
            "usage": r.get("usage", {}),
            **score_item(it, pred),
            **{
                f"cite_{k}": v
                for k, v in (
                    citation_checks(cls, r.get("events", []), con) if con else citation_checks(None, [], None)
                ).items()
            },
        }
        rows.append(row)
    return rows, aggregate(rows)


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    agg: dict = {
        "n": n,
        "n_stale": sum(r["stale"] for r in rows),
        "n_errors": sum(bool(r["error"]) for r in rows),
    }
    for k in LEVELS:
        elig = [r for r in rows if r[f"exact_{k}"] is not None]
        agg[f"acc_{k}"] = round(sum(r[f"exact_{k}"] for r in elig) / len(elig), 4) if elig else None
        agg[f"n_{k}"] = len(elig)
    fresh = [r for r in rows if not r["stale"]]
    stale = [r for r in rows if r["stale"]]
    agg["acc_10_nonstale"] = round(
        sum(bool(r["exact_10"]) for r in fresh if r["exact_10"] is not None)
        / max(1, sum(r["exact_10"] is not None for r in fresh)),
        4,
    )
    agg["acc_6_stale"] = round(sum(r["exact_6"] for r in stale) / len(stale), 4) if stale else None
    # Abstention: accuracy on answered items at the deepest scorable level.
    answered = [r for r in rows if not r["abstain"] and r["pred"]]
    deep = lambda r: r[f"exact_{r['scored_depth']}"]  # noqa: E731
    agg["abstain_rate"] = round(1 - len(answered) / max(1, n), 4)
    agg["acc_when_answering"] = round(sum(bool(deep(r)) for r in answered) / max(1, len(answered)), 4)
    agg["acc_deepest_all"] = round(sum(bool(deep(r)) for r in rows) / max(1, n), 4)
    conf_rows = [r for r in rows if isinstance(r["confidence"], int | float)]
    agg["ece"] = ece([float(r["confidence"]) for r in conf_rows], [bool(deep(r)) for r in conf_rows])
    agg["coverage_curve"] = coverage_curve(conf_rows, deep)
    # Citations.
    cited = sum(r["cite_n_cited"] for r in rows)
    agg["citations_total"] = cited
    agg["citation_valid_rate"] = round(sum(r["cite_valid"] for r in rows) / cited, 4) if cited else None
    agg["citation_hallucinated"] = sum(r["cite_hallucinated"] for r in rows)
    agg["citation_not_in_force"] = sum(r["cite_not_in_force"] for r in rows)
    agg["items_with_citation"] = sum(r["cite_n_cited"] > 0 for r in rows)
    # Cost, tokens, latency, cache.
    usd = [r["usd"] for r in rows]
    agg["usd_total"] = round(sum(usd), 4)
    agg["usd_per_item"] = round(sum(usd) / max(1, n), 5)
    agg["tokens_per_item"] = round(sum(r["tokens"] for r in rows) / max(1, n), 1)
    agg["tool_calls_per_item"] = round(sum(r["tool_calls"] for r in rows) / max(1, n), 2)
    # End-to-end wall time per classification (model calls plus tool calls). Only meaningful for interactive runs.
    lat = [r["wall_s"] for r in rows if r.get("wall_s")]
    agg["latency_p50_s"] = round(median(lat), 2) if lat else None
    agg["latency_p95_s"] = round(_pct(lat, 0.95), 2) if lat else None
    tin = sum(
        r["usage"].get("input_tokens", 0)
        + r["usage"].get("cache_read_tokens", 0)
        + r["usage"].get("cache_write_5m_tokens", 0)
        + r["usage"].get("cache_write_1h_tokens", 0)
        for r in rows
    )
    agg["cache_hit_rate"] = (
        round(sum(r["usage"].get("cache_read_tokens", 0) for r in rows) / tin, 4) if tin else None
    )
    return agg


def coverage_curve(rows: list[dict], deep) -> list[dict]:
    """Accuracy of the most confident fraction of items, for coverage 10% to 100%."""
    if not rows:
        return []
    s = sorted(rows, key=lambda r: -float(r["confidence"]))
    out = []
    for cov in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        k = max(1, round(cov * len(s)))
        out.append({"coverage": cov, "accuracy": round(sum(bool(deep(r)) for r in s[:k]) / k, 4)})
    return out
