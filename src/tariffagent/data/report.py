"""Summary of what the data layer holds."""

from __future__ import annotations

import json

from tariffagent.data.db import connect
from tariffagent.data.hts import current_rev


def data_report() -> dict:
    con = connect()
    rev = current_rev(con)
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]  # noqa: E731
    revs = {r["name"]: r["c"] for r in con.execute("SELECT rev name, COUNT(*) c FROM hts_rows GROUP BY rev")}
    rep: dict = {
        "hts_current_revision": rev,
        "hts_rows_current": revs.get(rev, 0),
        "hts_10digit_lines_current": q(
            "SELECT COUNT(*) FROM hts_rows WHERE rev=? AND length(digits)=10", rev
        ),
        "hts_revisions_held": revs,
        "notes": {
            r["scope"]: r["c"] for r in con.execute("SELECT scope, COUNT(*) c FROM notes GROUP BY scope")
        },
        "rulings_total": q("SELECT COUNT(*) FROM rulings"),
        "rulings_with_cross_meta": q("SELECT COUNT(*) FROM rulings WHERE has_meta=1"),
        "rulings_with_text": q("SELECT COUNT(*) FROM rulings WHERE text IS NOT NULL AND text != ''"),
        "rulings_by_collection": {
            r["collection"] or "?": r["c"]
            for r in con.execute("SELECT collection, COUNT(*) c FROM rulings GROUP BY collection")
        },
        "rulings_date_range_all": list(
            con.execute("SELECT MIN(date), MAX(date) FROM rulings WHERE date != ''").fetchone()
        ),
        "rulings_date_range_with_text": list(
            con.execute("SELECT MIN(date), MAX(date) FROM rulings WHERE date != '' AND text != ''").fetchone()
        ),
        "text_source": {
            r["source"]: r["c"]
            for r in con.execute("SELECT source, COUNT(*) c FROM rulings WHERE text != '' GROUP BY source")
        },
        "status_distribution": {
            r["status"]: r["c"]
            for r in con.execute("SELECT status, COUNT(*) c FROM ruling_status GROUP BY status")
        },
        "status_method": {
            r["method"]: r["c"]
            for r in con.execute("SELECT method, COUNT(*) c FROM ruling_status GROUP BY method")
        },
    }
    # Stale-code rate over codes cited by rulings that have text (the retrieval corpus).
    from tariffagent.data.crosswalk import Crosswalk

    cw = Crosswalk(con)
    codes = set()
    for r in con.execute("SELECT tariffs FROM rulings WHERE text != ''"):
        for t in json.loads(r["tariffs"] or "[]"):
            d = "".join(ch for ch in t if ch.isdigit())
            if len(d) == 10:
                codes.add(d)
    stale = sum(1 for c in codes if cw.map(c)["stale"])
    rep["corpus_distinct_10digit_codes"] = len(codes)
    rep["corpus_stale_code_rate"] = round(stale / max(1, len(codes)), 4)
    rep["eval_redactions"] = {
        r["dataset"]: r["c"]
        for r in con.execute(
            "SELECT dataset, COUNT(DISTINCT ruling_id) c FROM eval_redactions GROUP BY dataset"
        )
    }
    rep["dataset_crosswalk"] = _crosswalk_counts()
    idx = con.execute("SELECT name FROM sqlite_master WHERE name IN ('rulings_fts','hts_fts')").fetchall()
    rep["fts_tables"] = [r["name"] for r in idx]
    return rep


def _crosswalk_counts() -> dict:
    """How each fixed dataset's gold codes map to today's HTS (exact, mapped, stale)."""
    from collections import Counter

    from tariffagent.evals.datasets import load_dataset

    out = {}
    for name in ("atlas_test_200", "dev_100"):
        try:
            items = load_dataset(name)
        except FileNotFoundError:
            continue
        methods = Counter(it.get("crosswalk_method", "") for it in items)
        stale = sum(1 for it in items if it.get("code_stale"))
        out[name] = {
            "n": len(items),
            "methods": dict(methods),
            "stale": stale,
            "stale_rate": round(stale / len(items), 4),
        }
    return out
