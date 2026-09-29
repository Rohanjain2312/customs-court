#!/usr/bin/env python3
"""Validate a US HTS code.

Checks:
1. Format: 10 digits, written NNNN.NN.NN.NN (dots optional on input).
2. Existence: the code is a current 10-digit statistical line.
   - Uses the local TariffAgent database when TARIFFAGENT_DB points to it
     (or ./data/tariffagent.sqlite exists).
   - Otherwise asks the public USITC HTS search API (no key needed).

Exit code 0 when valid, 1 when invalid, 2 when existence could not be checked.
Standard library only.

Usage: python validate_hts.py 4202.21.60.00 [--json]
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request


def fmt(d: str) -> str:
    return f"{d[:4]}.{d[4:6]}.{d[6:8]}.{d[8:10]}"


def check_local(d: str, db: str) -> dict | None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rev = con.execute("SELECT name FROM revisions WHERE is_current=1").fetchone()
    if not rev:
        return None
    row = con.execute(
        "SELECT description, path, is_leaf FROM hts_rows WHERE rev=? AND digits=?", (rev[0], d)
    ).fetchone()
    if not row:
        near = con.execute(
            "SELECT code FROM hts_rows WHERE rev=? AND digits LIKE ? AND length(digits)=10 LIMIT 5", (rev[0], d[:8] + "%")
        ).fetchall()
        return {"exists": False, "revision": rev[0], "source": "local", "same_8_digit_lines": [n[0] for n in near]}
    return {"exists": True, "revision": rev[0], "source": "local", "description": row[0], "path": row[1], "is_leaf": bool(row[2])}


def check_remote(d: str) -> dict | None:
    url = "https://hts.usitc.gov/reststop/search?keyword=" + urllib.parse.quote(fmt(d))
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"error": f"USITC lookup failed: {e}"}
    for row in data:
        code = re.sub(r"\D", "", row.get("htsno") or "")
        if len(code) == 8:
            code += re.sub(r"\D", "", row.get("statisticalSuffix") or "")
        if code == d:
            return {"exists": True, "source": "usitc", "description": row.get("description", "")}
    return {"exists": False, "source": "usitc"}


def validate(code: str) -> tuple[int, dict]:
    d = re.sub(r"\D", "", code or "")
    out: dict = {"input": code, "digits": d}
    if len(d) != 10:
        out["valid"] = False
        out["error"] = f"Expected 10 digits, got {len(d)}. A complete US classification needs the statistical suffix."
        return 1, out
    out["formatted"] = fmt(d)
    db = os.environ.get("TARIFFAGENT_DB") or ("data/tariffagent.sqlite" if os.path.exists("data/tariffagent.sqlite") else "")
    res = check_local(d, db) if db else None
    if res is None:
        res = check_remote(d)
    out.update(res or {})
    if "error" in out and "exists" not in out:
        out["valid"] = None
        return 2, out
    out["valid"] = bool(out.get("exists")) and out.get("is_leaf", True)
    if out.get("exists") and out.get("is_leaf") is False:
        out["error"] = "Code exists but is not a statistical (leaf) line."
    return (0 if out["valid"] else 1), out


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    rc, out = validate(argv[0])
    if "--json" in argv:
        print(json.dumps(out, indent=2))
    else:
        status = "VALID" if out.get("valid") else ("UNCHECKED" if rc == 2 else "INVALID")
        print(f"{status} {out.get('formatted', out['input'])}: {out.get('description') or out.get('error', '')}")
        if out.get("same_8_digit_lines"):
            print("Current lines under the same 8 digits:", ", ".join(out["same_8_digit_lines"]))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
