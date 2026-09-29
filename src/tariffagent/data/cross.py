"""CBP CROSS rulings ingestion.

CROSS (rulings.cbp.gov) has no bulk API. The public web app uses a JSON API:
- GET /api/search?term=*&collection=ALL&commodityGrouping=ALL&pageSize=N&page=P&sortBy=DATE_DESC&fromDate=&toDate=
  returns metadata including tariffs and cross references (modifiedBy, revokedBy, ...).
  Hits are capped at 10,000 per query, so we page through monthly date windows.
- GET /api/ruling/<id> returns the full text.

robots.txt returned 404 on 2026-09-28. We still rate limit to about 1 request per
second, cache every raw response on disk and resume from the cache.

A community mirror on Hugging Face (orlandowhite/hts-cross-rulings, 54,558 rulings,
2000-01 to 2025-08, with original ruling text) seeds the text corpus. Texts are
spot-checked against CROSS (see verify_mirror_sample) and anything newer is fetched
from CROSS directly.
"""

from __future__ import annotations

import calendar
import json
import random
import re
from datetime import date, datetime

from tariffagent.config import get_settings
from tariffagent.data.db import connect
from tariffagent.data.http import PoliteClient

BASE = "https://rulings.cbp.gov/api"
MIRROR_URL = "https://huggingface.co/datasets/orlandowhite/hts-cross-rulings/resolve/main/cross_rulings.json"


def norm_id(rid: str) -> str:
    """'NY I84264' -> 'I84264', 'HQ 967123' -> '967123', 'n364781' -> 'N364781'."""
    rid = (rid or "").strip().upper()
    rid = re.sub(r"^(NY|HQ)\s+", "", rid)
    return rid.replace(" ", "")


def _client(sub: str, interval: float = 1.0) -> PoliteClient:
    return PoliteClient(get_settings().data_dir / "raw" / "cross" / sub, min_interval_s=interval)


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = calendar.monthrange(y, m)[1]
        yield date(y, m, 1), date(y, m, last)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def harvest_meta(start: date = date(1989, 1, 1), end: date | None = None, page_size: int = 500) -> dict:
    """Page through all rulings month by month and upsert metadata."""
    end = end or date.today()
    http = _client("search")
    con = connect()
    seen = 0
    for a, b in _months(start, end):
        page = 1
        while True:
            url = (
                f"{BASE}/search?term=*&collection=ALL&commodityGrouping=ALL&pageSize={page_size}"
                f"&page={page}&sortBy=DATE_DESC&fromDate={a.isoformat()}&toDate={b.isoformat()}"
            )
            # The current month is re-fetched so new rulings show up.
            fresh = a.year == end.year and a.month == end.month
            body = http.get_bytes(url, f"{a:%Y-%m}_p{page}.json", refresh=fresh)
            d = json.loads(body) if body else {"rulings": [], "totalHits": 0}
            if d.get("totalHits", 0) >= 10000:
                raise RuntimeError(f"Window {a}..{b} has >= 10000 hits; split it")
            for r in d["rulings"]:
                upsert_meta(con, r)
                seen += 1
            if page * page_size >= d.get("totalHits", 0) or not d["rulings"]:
                break
            page += 1
        con.commit()
    return {"meta_rows_seen": seen, "network_calls": http.network_calls}


def _j(x) -> str:
    return json.dumps([norm_id(i) for i in (x or [])])


def upsert_meta(con, r: dict) -> None:
    rid = norm_id(r["rulingNumber"])
    con.execute(
        """INSERT INTO rulings (id, collection, date, subject, tariffs, related, modified_by, modifies,
             revoked_by, revokes, operationally_revoked, categories, source, has_meta)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)
           ON CONFLICT(id) DO UPDATE SET collection=excluded.collection, date=excluded.date,
             subject=excluded.subject, tariffs=excluded.tariffs, related=excluded.related,
             modified_by=excluded.modified_by, modifies=excluded.modifies, revoked_by=excluded.revoked_by,
             revokes=excluded.revokes, operationally_revoked=excluded.operationally_revoked,
             categories=excluded.categories, has_meta=1""",
        (
            rid,
            (r.get("collection") or "").upper(),
            (r.get("rulingDate") or "")[:10],
            r.get("subject") or "",
            json.dumps([t.strip() for t in (r.get("tariffs") or "").split(",") if t.strip()]),
            _j(r.get("relatedRulings")),
            _j(r.get("modifiedBy")),
            _j(r.get("modifies")),
            _j(r.get("revokedBy")),
            _j(r.get("revokes")),
            int(bool(r.get("operationallyRevoked"))),
            r.get("categories") or "",
            "cross_meta",
        ),
    )


_IDRE = re.compile(r"\b([A-Z]\d{5}|H\d{6}|W\d{6}|\d{6})\b")
_CODE_RE = re.compile(r"\b\d{4}\.\d{2}\.\d{2}(?:\.?\d{2})?\b")
_W = re.compile(r"[a-z]{4,}")


def _words(s: str) -> set[str]:
    return set(_W.findall((s or "").lower())) - {
        "classification",
        "tariff",
        "from",
        "with",
        "ruling",
        "letter",
        "country",
        "origin",
    }


def load_mirror() -> dict:
    """Load full texts from the Hugging Face mirror, keeping only texts we can verify.

    The mirror's ruling_id does not always match its text (checked 2026-09-28: the
    text stored under 963787 is ruling I85020). A text is kept when:
    - own_header: its own id appears in the first 300 characters, or
    - rekeyed_by_header: another known ruling id appears there, and that ruling's
      CROSS codes appear in the text (or it has none), in which case the text is
      stored under that id, or
    - meta_code_match: CROSS lists codes for the id that appear in the text and the
      CROSS subject shares words with the text's opening.
    Everything else is dropped. Texts fetched from CROSS directly are never replaced.
    """
    s = get_settings()
    http = PoliteClient(s.data_dir / "raw" / "mirror", min_interval_s=0)
    data = json.loads(http.get_bytes(MIRROR_URL, "cross_rulings.json"))
    con = connect()
    meta = {
        r["id"]: (set(re.sub(r"\D", "", x)[:8] for x in json.loads(r["tariffs"] or "[]")), r["subject"] or "")
        for r in con.execute("SELECT id, tariffs, subject FROM rulings WHERE has_meta=1")
    }
    con.execute("UPDATE rulings SET text=NULL WHERE source LIKE 'mirror%'")
    stats: dict[str, int] = {}
    assigned: dict[str, tuple[str, str, dict]] = {}
    for r in data:
        rid = norm_id(r["ruling_id"])
        text = r.get("original_ruling_text") or ""
        if not text:
            stats["no_text"] = stats.get("no_text", 0) + 1
            continue
        head = text[:300]
        codes = {re.sub(r"\D", "", x)[:8] for x in _CODE_RE.findall(text)}
        how, target = None, None
        if rid in head:
            how, target = "own_header", rid
        else:
            hdr = [i for i in _IDRE.findall(head) if i in meta]
            if hdr and (not meta[hdr[0]][0] or meta[hdr[0]][0] & codes):
                how, target = "rekeyed_by_header", hdr[0]
            elif rid in meta and meta[rid][0] & codes:
                subj = _words(meta[rid][1])
                if subj and len(subj & _words(text[:1500])) / len(subj) >= 0.5:
                    how, target = "meta_code_match", rid
        if not how:
            stats["dropped_unverified"] = stats.get("dropped_unverified", 0) + 1
            continue
        if target in assigned:
            stats["duplicate"] = stats.get("duplicate", 0) + 1
            continue
        stats[how] = stats.get(how, 0) + 1
        assigned[target] = (text, how, r)
    for target, (text, how, r) in assigned.items():
        code = (r.get("hts_code") or "").strip()
        try:
            d = datetime.strptime(r["date"], "%b %d, %Y").date().isoformat()
        except (ValueError, TypeError):
            d = ""
        exists = con.execute("SELECT source FROM rulings WHERE id=?", (target,)).fetchone()
        if exists and exists["source"] == "cross":
            continue
        if exists:
            con.execute("UPDATE rulings SET text=?, source=? WHERE id=?", (text, f"mirror:{how}", target))
        else:
            con.execute(
                "INSERT INTO rulings (id, collection, date, subject, text, tariffs, source, has_meta) VALUES (?,?,?,?,?,?,?,0)",
                (
                    target,
                    "",
                    d,
                    r.get("short_product_description") or "",
                    text,
                    json.dumps([code] if code else []),
                    f"mirror:{how}",
                ),
            )
    # Drop mirror-only rows that ended up with no text.
    con.execute("DELETE FROM rulings WHERE has_meta=0 AND (text IS NULL OR text='')")
    con.commit()
    stats["kept"] = len(assigned)
    return stats


def fetch_text(rid: str, http: PoliteClient | None = None) -> dict | None:
    http = http or _client("rulings")
    body = http.get_bytes(f"{BASE}/ruling/{rid}", f"{rid}.json")
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def fetch_texts(ids: list[str], progress_every: int = 100) -> dict:
    http = _client("rulings")
    con = connect()
    got = missing = 0
    for i, rid in enumerate(ids):
        d = fetch_text(rid, http)
        if d and d.get("text"):
            con.execute("UPDATE rulings SET text=?, source='cross' WHERE id=?", (d["text"], rid))
            got += 1
        else:
            missing += 1
        if (i + 1) % progress_every == 0:
            con.commit()
            print(f"fetched {i + 1}/{len(ids)} (network calls {http.network_calls})", flush=True)
    con.commit()
    return {"fetched": got, "missing": missing, "network_calls": http.network_calls}


def ids_needing_text(since: str = "2025-07-01") -> list[str]:
    con = connect()
    rows = con.execute(
        "SELECT id FROM rulings WHERE (text IS NULL OR text='') AND date >= ? ORDER BY date DESC", (since,)
    ).fetchall()
    return [r["id"] for r in rows]


def verify_mirror_sample(n: int = 20, seed: int = 7) -> dict:
    """Compare mirror text against CROSS for a random sample. Returns match stats."""
    con = connect()
    ids = [
        r["id"]
        for r in con.execute("SELECT id FROM rulings WHERE source LIKE 'mirror%' AND text != '' ORDER BY id")
    ]
    random.Random(seed).shuffle(ids)
    http = _client("rulings")
    results = []
    for rid in ids[:n]:
        mine = con.execute("SELECT text FROM rulings WHERE id=?", (rid,)).fetchone()["text"]
        d = fetch_text(rid, http)
        if not d or not d.get("text"):
            results.append({"id": rid, "found": False})
            continue
        a = set(re.findall(r"\w+", mine.lower()))
        b = set(re.findall(r"\w+", d["text"].lower()))
        jac = len(a & b) / max(1, len(a | b))
        results.append({"id": rid, "found": True, "jaccard": round(jac, 3)})
    found = [r for r in results if r["found"]]
    return {
        "sampled": n,
        "found_on_cross": len(found),
        "median_jaccard": sorted(r["jaccard"] for r in found)[len(found) // 2] if found else None,
        "results": results,
    }
