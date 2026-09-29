"""Sample 50 rulings for the ruling_status check set and dump the evidence to read.

Strata: CROSS-metadata revoked (15), metadata modified (10), text-derived (10),
reverse links (5), and in_force rulings that a later HQ ruling mentions by number (10).
Evidence = every sentence in a linking or mentioning ruling that names the target.
"""

import json
import random
import re
import sys

from tariffagent.data import cross
from tariffagent.data.db import connect

rng = random.Random(20260928)
con = connect()


def pick(sql, n):
    ids = [r[0] for r in con.execute(sql)]
    rng.shuffle(ids)
    return ids[:n]


strata = {
    "meta_revoked": pick("SELECT id FROM ruling_status WHERE method='meta' AND status='revoked'", 15),
    "meta_modified": pick("SELECT id FROM ruling_status WHERE method='meta' AND status='modified'", 10),
    "text": pick("SELECT id FROM ruling_status WHERE method='text'", 10),
    "reverse_link": pick("SELECT id FROM ruling_status WHERE method='reverse_link'", 5),
}
# Hard negatives: in_force rulings named in some later HQ ruling's text.
hq = con.execute("SELECT id, text FROM rulings WHERE collection='HQ' AND text != '' AND date >= '2010-01-01'").fetchall()
rng.shuffle(hq)
mentioned = []
for r in hq:
    for m in re.findall(r"\b(?:NY|HQ)\s+([A-Z]?\d{5,6})\b", r["text"]):
        st = con.execute("SELECT status FROM ruling_status WHERE id=?", (m,)).fetchone()
        if st and st[0] == "in_force" and m != r["id"] and m not in mentioned:
            mentioned.append(m)
            break
    if len(mentioned) >= 10:
        break
strata["mentioned_in_force"] = mentioned

http = cross._client("rulings")


def text_of(rid):
    row = con.execute("SELECT text FROM rulings WHERE id=?", (rid,)).fetchone()
    if row and row[0]:
        return row[0]
    d = cross.fetch_text(rid, http)
    return (d or {}).get("text") or ""


def sentences_naming(text, target):
    sents = re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", text))
    return [s[:500] for s in sents if target in s][:6]


out = []
for stratum, ids in strata.items():
    for rid in ids:
        row = con.execute(
            "SELECT r.id, r.date, r.subject, r.revoked_by, r.modified_by, s.status, s.method, s.linked "
            "FROM rulings r JOIN ruling_status s USING(id) WHERE r.id=?",
            (rid,),
        ).fetchone()
        linked = set(json.loads(row["linked"])) | set(json.loads(row["revoked_by"] or "[]")) | set(json.loads(row["modified_by"] or "[]"))
        if stratum == "mentioned_in_force":
            linked |= {h["id"] for h in hq if rid in (h["text"] or "")}
        ev = {}
        for lid in sorted(linked)[:4]:
            ev[lid] = sentences_naming(text_of(lid), rid)
        out.append({"id": rid, "stratum": stratum, "date": row["date"], "subject": row["subject"][:200],
                    "derived_status": row["status"], "method": row["method"], "linked": sorted(linked), "evidence": ev})
json.dump(out, open("evals/status_check/evidence.json", "w"), indent=1)
print(len(out), {k: len(v) for k, v in strata.items()}, file=sys.stderr)
