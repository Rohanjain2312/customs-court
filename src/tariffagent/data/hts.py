"""USITC Harmonized Tariff Schedule ingestion.

Sources (checked 2026-09-28):
- Current tree: https://hts.usitc.gov/reststop/exportList?from=0100&to=9999.99.99.99&format=JSON&styles=false
- Release list: https://hts.usitc.gov/reststop/releaseList
- Chapter notes (HTML): https://hts.usitc.gov/reststop/getChapterNotes?doc=<chapter>
- Section notes (HTML): https://hts.usitc.gov/reststop/getSectionNotes?doc=<first chapter of section>
- GRI (PDF): https://hts.usitc.gov/reststop/file?release=currentRelease&filename=General Rules of Interpretation
- Past editions (JSON): https://www.usitc.gov/sites/default/files/tata/hts/hts_<year>_basic...json
"""

from __future__ import annotations

import io
import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from pypdf import PdfReader

from tariffagent.config import get_settings
from tariffagent.data.db import connect
from tariffagent.data.http import PoliteClient

API = "https://hts.usitc.gov/reststop"
ARCHIVE = "https://www.usitc.gov/sites/default/files/tata/hts"

# Basic editions used for the time machine and revision diffs.
PAST_EDITIONS = {
    "2018Basic": "hts_2018_basic_json_0.json",
    "2019Basic": "hts_2019_basic_data.json",
    "2020BasicB": "hts_2020_revision_basicb_json.json",
    "2021Basic": "hts_2021_revision_basic_json.json",
    "2022Basic": "hts_2022_basic_json.json",
    "2023Basic": "hts_2023_basic_edition_json.json",
    "2024Basic": "hts_2024_basic_edition_json.json",
    "2025Basic": "hts_2025_basic_edition_json.json",
    "2026Basic": "hts_2026_basic_edition_json.json",
}

SECTIONS: list[tuple[str, int, int, str]] = [
    ("I", 1, 5, "Live animals; animal products"),
    ("II", 6, 14, "Vegetable products"),
    ("III", 15, 15, "Animal, vegetable or microbial fats and oils"),
    ("IV", 16, 24, "Prepared foodstuffs; beverages, spirits and vinegar; tobacco"),
    ("V", 25, 27, "Mineral products"),
    ("VI", 28, 38, "Products of the chemical or allied industries"),
    ("VII", 39, 40, "Plastics and rubber and articles thereof"),
    ("VIII", 41, 43, "Raw hides, skins, leather, furskins; travel goods, handbags"),
    ("IX", 44, 46, "Wood, cork, straw and plaiting materials"),
    ("X", 47, 49, "Pulp of wood; paper and paperboard"),
    ("XI", 50, 63, "Textiles and textile articles"),
    ("XII", 64, 67, "Footwear, headgear, umbrellas"),
    ("XIII", 68, 70, "Articles of stone, plaster, cement; ceramic products; glass"),
    ("XIV", 71, 71, "Pearls, precious stones and metals; imitation jewelry; coin"),
    ("XV", 72, 83, "Base metals and articles of base metal"),
    ("XVI", 84, 85, "Machinery and mechanical appliances; electrical equipment"),
    ("XVII", 86, 89, "Vehicles, aircraft, vessels and associated transport equipment"),
    ("XVIII", 90, 92, "Optical, photographic, measuring, medical instruments; clocks; musical instruments"),
    ("XIX", 93, 93, "Arms and ammunition"),
    ("XX", 94, 96, "Miscellaneous manufactured articles"),
    ("XXI", 97, 97, "Works of art, collectors' pieces and antiques"),
    ("XXII", 98, 99, "Special classification provisions; temporary legislation"),
]


def section_for_chapter(ch: int) -> str:
    for sec, a, b, _ in SECTIONS:
        if a <= ch <= b:
            return sec
    return ""


def digits(code: str) -> str:
    return re.sub(r"\D", "", code or "")


def format_code(d: str) -> str:
    """Format a digit string as an HTS code: 8471.30.01.00."""
    d = digits(d)
    if len(d) <= 4:
        return d
    parts = [d[:4], d[4:6], d[6:8], d[8:10]]
    return ".".join(p for p in parts if p)


def _clean(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def build_rows(rev: str, raw: list[dict]) -> list[dict]:
    """Turn the flat USITC export into rows with parent links and a readable path."""
    rows: list[dict] = []
    stack: list[tuple[int, int]] = []  # (indent, idx)
    for i, r in enumerate(raw):
        code = (r.get("htsno") or "").strip()
        try:
            indent = int(r.get("indent") or 0)
        except ValueError:
            indent = 0
        d = digits(code)
        # A new 4-digit heading always starts at the top of the stack.
        if len(d) == 4:
            stack = []
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent_idx = stack[-1][1] if stack else -1
        desc = _clean(r.get("description"))
        path = (rows[parent_idx]["path"] + " > " if parent_idx >= 0 else "") + desc
        heading_d = d[:4] if d else (rows[parent_idx]["heading"] if parent_idx >= 0 else "")
        ch = heading_d[:2] if heading_d else ""
        units = r.get("units") or []
        if isinstance(units, str):
            units = [units] if units else []
        row = {
            "rev": rev,
            "idx": i,
            "code": format_code(d) if d else "",
            "digits": d,
            "indent": indent,
            "description": desc,
            "path": path[-2000:],
            "parent_idx": parent_idx,
            "chapter": ch,
            "heading": heading_d,
            "section": section_for_chapter(int(ch)) if ch.isdigit() else "",
            "general": _clean(r.get("general")),
            "special": _clean(r.get("special")),
            "other": _clean(r.get("other")),
            "units": json.dumps(units),
            "footnotes": json.dumps(r.get("footnotes") or []),
            "is_leaf": 1,
        }
        if parent_idx >= 0:
            rows[parent_idx]["is_leaf"] = 0
        rows.append(row)
        stack.append((indent, i))
    return rows


def _store_rows(con, rev: str, rows: list[dict]) -> None:
    con.execute("DELETE FROM hts_rows WHERE rev=?", (rev,))
    cols = list(rows[0].keys())
    con.executemany(
        f"INSERT INTO hts_rows ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [tuple(r[c] for c in cols) for r in rows],
    )


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for li in soup.find_all("li"):
        li.insert_before("\n")
    for div in soup.find_all("div"):
        div.insert_before("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def ingest(refresh: bool = False, past: bool = True) -> dict:
    s = get_settings()
    raw_dir = s.data_dir / "raw" / "hts"
    http = PoliteClient(raw_dir, min_interval_s=0.5)
    con = connect()

    releases = json.loads(http.get_bytes(f"{API}/releaseList", "releaseList.json", refresh=refresh))
    cur = next(r for r in releases if r.get("status") == "current")
    cur_name = cur["name"]
    con.execute("UPDATE revisions SET is_current=0")
    con.execute(
        "INSERT OR REPLACE INTO revisions VALUES (?,?,?,?,?,1)",
        (cur_name, cur.get("title") or cur.get("description"), int(cur_name[:4]), cur.get("date"), "hts.usitc.gov exportList"),
    )
    raw = json.loads(
        http.get_bytes(
            f"{API}/exportList?from=0100&to=9999.99.99.99&format=JSON&styles=false",
            f"current_{cur_name}.json",
            refresh=refresh,
        )
    )
    _store_rows(con, cur_name, build_rows(cur_name, raw))

    if past:
        for name, fname in PAST_EDITIONS.items():
            b = http.get_bytes(f"{ARCHIVE}/{fname}", f"archive_{fname}")
            if b is None:
                continue
            con.execute(
                "INSERT OR REPLACE INTO revisions VALUES (?,?,?,?,?,0)",
                (name, f"{name[:4]} Basic Edition", int(name[:4]), f"{name[:4]}-01-01", f"usitc.gov archive {fname}"),
            )
            _store_rows(con, name, build_rows(name, json.loads(b)))

    # Notes for the current release.
    chapters = sorted({r["chapter"] for r in con.execute("SELECT DISTINCT chapter FROM hts_rows WHERE rev=?", (cur_name,)) if r["chapter"]})
    for ch in chapters:
        b = http.get_bytes(f"{API}/getChapterNotes?doc={int(ch)}", f"notes/chapter_{ch}.html")
        if b:
            txt = html_to_text(b.decode("utf-8", "replace"))
            con.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?)", (cur_name, "chapter", ch, f"Chapter {int(ch)} notes", txt))
    for sec, a, _b, title in SECTIONS:
        b = http.get_bytes(f"{API}/getSectionNotes?doc={a}", f"notes/section_{sec}.html")
        if b:
            txt = html_to_text(b.decode("utf-8", "replace"))
            con.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?)", (cur_name, "section", sec, f"Section {sec}: {title}", txt))
    gri_pdf = http.get_bytes(
        f"{API}/file?release=currentRelease&filename={quote('General Rules of Interpretation')}", "gri.pdf"
    )
    if gri_pdf:
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(gri_pdf)).pages)
        con.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?)", (cur_name, "gri", "GRI", "General Rules of Interpretation", text.strip()))
    con.commit()
    n = con.execute("SELECT rev, COUNT(*) c FROM hts_rows GROUP BY rev").fetchall()
    return {"current": cur_name, "rows": {r["rev"]: r["c"] for r in n}, "network_calls": http.network_calls}


def current_rev(con=None) -> str:
    con = con or connect(readonly=True)
    r = con.execute("SELECT name FROM revisions WHERE is_current=1").fetchone()
    return r["name"] if r else ""
