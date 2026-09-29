"""Derive ruling status (in_force | modified | revoked | unknown) from cross references.

Signals, strongest first:
1. CROSS metadata on the ruling itself: revokedBy, modifiedBy, operationallyRevoked.
2. Reverse links: another ruling lists this one in its `revokes` or `modifies` field.
3. Text of later HQ rulings: sentences such as "NY N123456 is hereby revoked" or
   "we are modifying HQ 950000". Only used when 1 and 2 are silent.
A ruling with CROSS metadata and no signal is in_force. A ruling we only hold from
the mirror, with no CROSS metadata, is unknown.

This is a heuristic. Its accuracy is measured on a hand-labeled check set
(evals/status_check/labels.jsonl) and reported in docs/EVAL.md.
"""

from __future__ import annotations

import json
import re

from tariffagent.data.db import connect

ID_PAT = r"(?:NY|HQ|N\.Y\.|H\.Q\.)?\s*([A-Z]?\d{5,6})"
REVOKE_RE = re.compile(
    r"(?:revok\w*|revocation of)\b[^.;]{0,160}?"
    + ID_PAT
    + r"|"
    + ID_PAT
    + r"[^.;]{0,120}?\b(?:is|are) (?:hereby )?revoked"
    + r"|"
    + ID_PAT
    + r",?\s+(?:is\s+)?revoked\b",
    re.I,
)
MODIFY_RE = re.compile(
    r"(?:modif\w*|modification of)\b[^.;]{0,160}?"
    + ID_PAT
    + r"|"
    + ID_PAT
    + r"[^.;]{0,120}?\b(?:is|are) (?:hereby )?modified"
    + r"|"
    + ID_PAT
    + r",?\s+(?:is\s+)?modified\b",
    re.I,
)
PROPOSED_RE = re.compile(r"\bpropos\w*", re.I)
# v2: sentences that talk about a revocation without making one.
# Lowercase only, so the month "May" does not count as "may".
NEGATION_RE = re.compile(
    r"\b(not|never|denied|deny|declin\w*|request\w*|whether|would|may|might|could|discretion|interim|pendency)\b"
)


def _ids(m: re.Match) -> list[str]:
    return [g.upper() for g in m.groups() if g]


def text_actions(text: str) -> dict[str, set[str]]:
    """Find rulings a text says it revokes or modifies. Skips sentences about proposals."""
    out = {"revokes": set(), "modifies": set()}
    for sent in re.split(r"(?<=[.;])\s+", text or ""):
        if PROPOSED_RE.search(sent) and not re.search(r"hereby|final", sent, re.I):
            continue
        if NEGATION_RE.search(sent) and not re.search(r"\bhereby\b|^\s*RE:|\bRE:", sent):
            continue
        for m in REVOKE_RE.finditer(sent):
            out["revokes"].update(_ids(m))
        for m in MODIFY_RE.finditer(sent):
            out["modifies"].update(_ids(m))
    out["modifies"] -= out["revokes"]
    return out


def derive_all(con=None, use_text: bool = True) -> dict:
    con = con or connect()
    rows = con.execute(
        "SELECT id, date, collection, text, has_meta, modified_by, revoked_by, modifies, revokes, operationally_revoked "
        "FROM rulings"
    ).fetchall()
    rev_in: dict[str, set[str]] = {}
    mod_in: dict[str, set[str]] = {}
    txt_rev: dict[str, set[str]] = {}
    txt_mod: dict[str, set[str]] = {}
    known = {r["id"] for r in rows}
    for r in rows:
        for t in json.loads(r["revokes"] or "[]"):
            rev_in.setdefault(t, set()).add(r["id"])
        for t in json.loads(r["modifies"] or "[]"):
            mod_in.setdefault(t, set()).add(r["id"])
        if use_text and r["text"] and (r["collection"] == "HQ" or r["id"].startswith("H")):
            acts = text_actions(r["text"])
            for t in acts["revokes"]:
                if t != r["id"] and t in known:
                    txt_rev.setdefault(t, set()).add(r["id"])
            for t in acts["modifies"]:
                if t != r["id"] and t in known:
                    txt_mod.setdefault(t, set()).add(r["id"])
    counts: dict[str, int] = {}
    con.execute("DELETE FROM ruling_status")
    for r in rows:
        rid = r["id"]
        rb = set(json.loads(r["revoked_by"] or "[]"))
        mb = set(json.loads(r["modified_by"] or "[]"))
        if rb or r["operationally_revoked"]:
            st, linked, method = "revoked", rb, "meta"
        elif rid in rev_in:
            st, linked, method = "revoked", rev_in[rid], "reverse_link"
        elif mb:
            st, linked, method = "modified", mb, "meta"
        elif rid in mod_in:
            st, linked, method = "modified", mod_in[rid], "reverse_link"
        elif rid in txt_rev:
            st, linked, method = "revoked", txt_rev[rid], "text"
        elif rid in txt_mod:
            st, linked, method = "modified", txt_mod[rid], "text"
        elif r["has_meta"]:
            st, linked, method = "in_force", set(), "meta_no_signal"
        else:
            st, linked, method = "unknown", set(), "no_meta"
        counts[st] = counts.get(st, 0) + 1
        con.execute(
            "INSERT INTO ruling_status VALUES (?,?,?,?,?)",
            (rid, st, json.dumps(sorted(linked)), method, ""),
        )
    con.commit()
    return counts


def get_status(con, rid: str) -> dict:
    r = con.execute("SELECT * FROM ruling_status WHERE id=?", (rid,)).fetchone()
    if not r:
        return {"id": rid, "status": "unknown", "linked": [], "method": "not_in_corpus"}
    return {"id": rid, "status": r["status"], "linked": json.loads(r["linked"]), "method": r["method"]}
