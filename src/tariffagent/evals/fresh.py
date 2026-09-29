"""Build the fresh evaluation set from CROSS rulings dated after the newest training cutoff.

Newest cutoff among models in use: Claude Sonnet 5.5, training data through June
2026 (models overview page, checked 2026-09-28). Haiku 4.5: July 2025. gpt-5-mini
is older. So fresh = rulings dated 2026-07-01 or later.

The product description is cut from the ruling's own facts section with a fixed
rule (no model involved): keep the sentences between the request and the holding,
drop every sentence that mentions a code, heading, HTSUS, classification or a
suggested classification. That keeps the answer out of the input.
"""

from __future__ import annotations

import json
import random
import re

from tariffagent.data.db import connect
from tariffagent.evals.datasets import write_dataset

FRESH_FROM = "2026-07-01"
LEAK = re.compile(
    r"\d{4}\.\d{2}|\bheading|\bsubheading|HTSUS|HTS\b|Harmonized|classif|Chapter \d|chapter \d|GRI\b|General Rule|"
    r"Explanatory Note|\bEN\b|duty|ad valorem|tariff|ruling|NY [A-Z]?\d{5}|HQ [A-Z]?\d{5}|CBP|Customs",
    re.I,
)
START = re.compile(
    r"(requested a (tariff )?classification ruling[^.]*\.|you requested a ruling[^.]*\.|Dear [^:]{1,60}:)",
    re.I,
)
STOP = re.compile(
    r"The applicable subheading|In your (letter|request|submission),? you (suggest|propose)|You (suggest|propose)|Classification under the HTSUS|LAW AND ANALYSIS|The General Rules",
    re.I,
)


def extract_description(text: str, max_chars: int = 1400) -> str:
    t = re.sub(r"\s+", " ", text or "")
    m = START.search(t)
    body = t[m.end() :] if m else t
    s = STOP.search(body)
    if s:
        body = body[: s.start()]
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", body)
    keep = []
    for sent in sents:
        if LEAK.search(sent):
            continue
        if (
            re.search(r"sample|photograph|literature|returned|destroyed|laboratory", sent, re.I)
            and len(sent) < 160
        ):
            continue
        keep.append(sent.strip())
    out = " ".join(k for k in keep if k)
    return out[:max_chars].rsplit(" ", 1)[0] if len(out) > max_chars else out


def build_fresh(max_items: int = 300, seed: int = 13) -> dict:
    con = connect()
    rows = con.execute(
        "SELECT id, date, subject, tariffs, text FROM rulings WHERE date >= ? AND text != '' ORDER BY id",
        (FRESH_FROM,),
    ).fetchall()
    items = []
    skipped = {"codes": 0, "short_description": 0}
    for r in rows:
        codes = [
            t
            for t in json.loads(r["tariffs"] or "[]")
            if len(re.sub(r"\D", "", t)) == 10 and not t.startswith("99")
        ]
        if len(codes) != 1 or not re.search(r"classification", r["subject"] or "", re.I):
            skipped["codes"] += 1
            continue
        desc = extract_description(r["text"])
        if len(desc) < 80:
            skipped["short_description"] += 1
            continue
        d = re.sub(r"\D", "", codes[0])
        items.append(
            {
                "item_id": f"fresh_{r['id']}",
                "ruling_id": r["id"],
                "ruling_date": r["date"],
                "description": desc,
                "gold_code": codes[0],
                "gold_digits": d,
                "gold_current": d,
                "crosswalk_method": "exact",
                "code_stale": False,
                "reference_reasoning": "",
            }
        )
    rng = random.Random(seed)
    rng.shuffle(items)
    items = sorted(items[:max_items], key=lambda x: x["item_id"])
    # Redact each golden ruling and any later ruling that names it.
    con.execute("DELETE FROM eval_redactions WHERE dataset LIKE 'fresh%'")
    name = f"fresh_{len(items)}"
    later = con.execute(
        "SELECT id, text FROM rulings WHERE date >= ? AND text != ''", (FRESH_FROM,)
    ).fetchall()
    for it in items:
        con.execute(
            "INSERT OR REPLACE INTO eval_redactions VALUES (?,?,?,?,?)",
            (it["ruling_id"], name, it["item_id"], 1.0, "self"),
        )
        for lr in later:
            if lr["id"] != it["ruling_id"] and it["ruling_id"] in (lr["text"] or ""):
                con.execute(
                    "INSERT OR REPLACE INTO eval_redactions VALUES (?,?,?,?,?)",
                    (lr["id"], name, it["item_id"], 1.0, "names_golden"),
                )
    con.commit()
    dates = [it["ruling_date"] for it in items]
    meta = {
        "source": "CBP CROSS (rulings.cbp.gov) full text, fetched 2026-09-28",
        "split": f"rulings dated {FRESH_FROM} or later, one 10-digit code, description cut from the ruling facts by rule",
        "date_range": [min(dates), max(dates)],
        "candidates": len(rows),
        "skipped": skipped,
        "use": "reported separately from ATLAS (post training cutoff)",
    }
    return {name: write_dataset(name, items, meta)}
