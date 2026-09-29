"""Map codes from older rulings to the current HTS where a clean mapping exists.

Rules, in order:
1. exact: the 10-digit code exists in the current release.
2. desc_match: the code exists in a past edition we hold, and exactly one current
   code under the same 6-digit subheading has the same normalized description.
3. single_child: the 8-digit subheading exists today with exactly one 10-digit line.
Anything else is stale (code_stale=True) and is scored at 6 digits.
"""

from __future__ import annotations

import re

from tariffagent.data.db import connect
from tariffagent.data.hts import current_rev, format_code


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


class Crosswalk:
    def __init__(self, con=None):
        self.con = con or connect()
        self.rev = current_rev(self.con)
        self.cur10: set[str] = set()
        self.cur_by8: dict[str, list[str]] = {}
        self.cur6_desc: dict[str, dict[str, list[str]]] = {}
        self.cur_any: set[str] = set()
        for r in self.con.execute(
            "SELECT digits, description FROM hts_rows WHERE rev=? AND digits!=''", (self.rev,)
        ):
            d = r["digits"]
            self.cur_any.add(d)
            if len(d) == 10:
                self.cur10.add(d)
                self.cur_by8.setdefault(d[:8], []).append(d)
                self.cur6_desc.setdefault(d[:6], {}).setdefault(_norm(r["description"]), []).append(d)
        self.past_desc: dict[str, str] = {}
        for r in self.con.execute(
            "SELECT h.digits, h.description FROM hts_rows h JOIN revisions v ON v.name=h.rev "
            "WHERE v.is_current=0 AND length(h.digits)=10 ORDER BY v.year"
        ):
            self.past_desc[r["digits"]] = r["description"]  # latest edition wins

    def map(self, code: str) -> dict:
        d = re.sub(r"\D", "", code or "")
        if len(d) == 10 and d in self.cur10:
            return {"code": d, "current_code": d, "method": "exact", "stale": False}
        if len(d) == 8 and d in self.cur_any:
            kids = self.cur_by8.get(d, [])
            if len(kids) == 1:
                return {"code": d, "current_code": kids[0], "method": "single_child_8", "stale": False}
            return {"code": d, "current_code": d, "method": "exact_8", "stale": False}
        if len(d) == 10 and d in self.past_desc:
            hits = self.cur6_desc.get(d[:6], {}).get(_norm(self.past_desc[d]), [])
            if len(hits) == 1:
                return {"code": d, "current_code": hits[0], "method": "desc_match", "stale": False}
        if len(d) >= 8:
            kids = self.cur_by8.get(d[:8], [])
            if len(kids) == 1:
                return {"code": d, "current_code": kids[0], "method": "single_child", "stale": False}
        return {"code": d, "current_code": None, "method": "none", "stale": True}

    def exists(self, code: str) -> bool:
        return re.sub(r"\D", "", code or "") in self.cur_any

    def store(self, codes: list[str]) -> dict:
        n_stale = 0
        for c in codes:
            m = self.map(c)
            n_stale += m["stale"]
            self.con.execute(
                "INSERT OR REPLACE INTO crosswalk VALUES (?,?,?,?)",
                (m["code"], m["current_code"], m["method"], int(m["stale"])),
            )
        self.con.commit()
        return {"codes": len(codes), "stale": n_stale}


def pretty(d: str | None) -> str | None:
    return format_code(d) if d else None
