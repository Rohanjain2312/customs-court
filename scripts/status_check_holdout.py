"""Held-out check for status heuristic v2: 15 text-derived cases not in the first
check set, plus 5 rulings that v1 flagged from text but v2 no longer flags."""

import json
import random
import re

from tariffagent.data import cross
from tariffagent.data.db import connect
from tariffagent.data.status import text_actions

rng = random.Random(7)
con = connect()
labeled = {json.loads(line)["id"] for line in open("evals/status_check/labels.jsonl")}
text_ids = [
    r[0] for r in con.execute("SELECT id FROM ruling_status WHERE method='text'") if r[0] not in labeled
]
rng.shuffle(text_ids)
v2 = text_ids[:15]

# Rebuild v1 text flags: rulings named in HQ text with a revoke/modify word, now in_force.
v1_re = re.compile(r"(?:revok\w*|modif\w*)[^.;]{0,160}?(?:NY|HQ)?\s*([A-Z]?\d{5,6})", re.I)
dropped = []
hq = con.execute(
    "SELECT id, text FROM rulings WHERE (collection='HQ' OR id LIKE 'H%') AND text != ''"
).fetchall()
rng.shuffle(hq)
for r in hq:
    now = text_actions(r["text"])
    for m in v1_re.finditer(r["text"]):
        t = m.group(1).upper()
        if t == r["id"] or t in now["revokes"] | now["modifies"] or t in labeled:
            continue
        st = con.execute("SELECT status, method FROM ruling_status WHERE id=?", (t,)).fetchone()
        if st and st[0] == "in_force" and st[1] == "meta_no_signal":
            dropped.append((t, r["id"]))
            break
    if len(dropped) >= 5:
        break

http = cross._client("rulings")


def text_of(rid):
    row = con.execute("SELECT text FROM rulings WHERE id=?", (rid,)).fetchone()
    return (row[0] if row and row[0] else (cross.fetch_text(rid, http) or {}).get("text", "")) or ""


out = []
for rid in v2:
    st = con.execute("SELECT status, linked FROM ruling_status WHERE id=?", (rid,)).fetchone()
    ev = {}
    for lid in json.loads(st["linked"])[:2]:
        sents = re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", text_of(lid)))
        ev[lid] = [s[:400] for s in sents if rid in s][:4]
    out.append({"id": rid, "stratum": "holdout_text_v2", "derived_status": st["status"], "evidence": ev})
for rid, src in dropped:
    sents = re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", text_of(src)))
    out.append(
        {
            "id": rid,
            "stratum": "holdout_dropped_by_v2",
            "derived_status": "in_force",
            "evidence": {src: [s[:400] for s in sents if rid in s][:4]},
        }
    )
json.dump(out, open("evals/status_check/holdout_evidence.json", "w"), indent=1)
for i, x in enumerate(out):
    print(f"=== [{i}] {x['id']} {x['stratum']} derived={x['derived_status']}")
    for lid, ss in x["evidence"].items():
        for s in ss[:3]:
            print(f"  [{lid}] {s[:300]}")
