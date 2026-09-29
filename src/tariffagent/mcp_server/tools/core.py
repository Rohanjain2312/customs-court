"""The one tool implementation shared by stdio, HTTP, the agents and the demo."""

from __future__ import annotations

import json
import re
import sqlite3
import threading

from tariffagent.config import get_settings
from tariffagent.data.db import connect
from tariffagent.data.hts import SECTIONS, current_rev, digits, format_code
from tariffagent.data.status import get_status
from tariffagent.index.search import HybridSearch
from tariffagent.mcp_server.schemas import (
    CrossSearchResult,
    GriResult,
    HtsNode,
    HtsSearchHit,
    HtsSearchResult,
    NavigateResult,
    NoteRef,
    NotesResult,
    RevisionDiffResult,
    RulingHit,
    RulingResult,
    RulingStatusResult,
    UntrustedText,
)

GRI_SUMMARY = [
    "GRI 1: classify by the terms of the headings and any section or chapter notes.",
    "GRI 2(a): incomplete or unassembled articles take the heading of the complete article if they have its essential character.",
    "GRI 2(b): mixtures and composite goods of a material are covered by headings naming that material; then apply GRI 3.",
    "GRI 3(a): the most specific description is preferred.",
    "GRI 3(b): mixtures, composite goods and retail sets are classified by the component giving essential character.",
    "GRI 3(c): otherwise, the heading that occurs last in numerical order.",
    "GRI 4: goods not covered above go to the heading of the most akin goods.",
    "GRI 5: cases and packing materials presented with goods.",
    "GRI 6: subheadings are compared only with subheadings at the same level, using GRI 1 to 5 mutatis mutandis.",
]

_WORD = re.compile(r"[a-z0-9]{3,}")


def _level(d: str) -> str:
    return {4: "heading", 6: "subheading", 8: "tariff_item", 10: "statistical"}.get(len(d), "statistical")


def wrap(source: str, text: str, limit: int, offset: int = 0) -> UntrustedText:
    text = text or ""
    total = len(text)
    chunk = text[offset : offset + limit]
    # Neutralize anything that imitates our own wrapper markers.
    chunk = chunk.replace("untrusted_corpus_text", "untrusted-corpus-text")
    return UntrustedText(source=source, content=chunk, truncated=offset + limit < total, total_chars=total)


def best_snippet(text: str, query: str, width: int = 500) -> str:
    text = re.sub(r"\s+", " ", text or "")
    if len(text) <= width:
        return text
    q = set(_WORD.findall(query.lower()))
    best, best_i = -1, 0
    for i in range(0, max(1, len(text) - width), width // 4):
        s = len(q & set(_WORD.findall(text[i : i + width].lower())))
        if s > best:
            best, best_i = s, i
    return text[best_i : best_i + width]


class TariffTools:
    """Implements all MCP tools over the local SQLite store."""

    def __init__(
        self,
        con: sqlite3.Connection | None = None,
        redact_eval: bool | None = None,
        use_vectors: bool | None = None,
    ):
        s = get_settings()
        self.con = con or connect(readonly=True)
        self.limit = s.tool_text_limit
        self.rev = current_rev(self.con)
        self.redact_eval = s.redact_eval if redact_eval is None else redact_eval
        self.search = HybridSearch(
            self.con, use_vectors=s.use_vectors if use_vectors is None else use_vectors
        )
        self._lock = threading.Lock()
        self.redacted: set[str] = set()
        if self.redact_eval:
            self.redacted = {r[0] for r in self.con.execute("SELECT DISTINCT ruling_id FROM eval_redactions")}

    # ---------- helpers ----------
    def _q(self, sql: str, *args):
        with self._lock:
            return self.con.execute(sql, args).fetchall()

    def _row_to_node(self, r) -> HtsNode:
        return HtsNode(
            code=r["code"],
            description=r["description"],
            path=r["path"],
            indent=r["indent"],
            is_leaf=bool(r["is_leaf"]),
            chapter=r["chapter"],
            heading=r["heading"],
            section=r["section"],
            general_rate=r["general"] or "",
            special_rate=(r["special"] or "")[:300],
            other_rate=r["other"] or "",
            units=json.loads(r["units"] or "[]"),
        )

    def _find_row(self, code: str, rev: str | None = None):
        d = digits(code)
        rows = self._q(
            "SELECT * FROM hts_rows WHERE rev=? AND digits=? ORDER BY idx LIMIT 1", rev or self.rev, d
        )
        return rows[0] if rows else None

    def _numbered_children(self, rev: str, idx: int) -> list:
        out = []
        for c in self._q("SELECT * FROM hts_rows WHERE rev=? AND parent_idx=? ORDER BY idx", rev, idx):
            if c["code"]:
                out.append(c)
            else:
                out.extend(self._numbered_children(rev, c["idx"]))
        return out

    def _note_excerpt(self, scope: str, nid: str, n: int = 1500) -> NoteRef | None:
        rows = self._q("SELECT title, text FROM notes WHERE rev=? AND scope=? AND id=?", self.rev, scope, nid)
        if not rows:
            return None
        return NoteRef(
            scope=scope,
            id=nid,
            title=rows[0]["title"],
            excerpt=wrap(f"HTS {scope} {nid} notes", rows[0]["text"], n),
        )

    def _visible(self, rid: str) -> bool:
        return rid not in self.redacted

    def _ruling_row(self, rid: str):
        rid = rid.strip().upper().replace("NY ", "").replace("HQ ", "").replace(" ", "")
        if not self._visible(rid):
            return None
        rows = self._q("SELECT * FROM rulings WHERE id=?", rid)
        return rows[0] if rows else None

    def _status(self, rid: str) -> dict:
        with self._lock:
            st = get_status(self.con, rid)
        st["linked"] = [x for x in st["linked"] if self._visible(x)]
        return st

    # ---------- tools ----------
    def hts_navigate(self, code: str) -> NavigateResult:
        d = digits(code)
        if len(d) == 2:
            heads = self._q(
                "SELECT * FROM hts_rows WHERE rev=? AND chapter=? AND indent=0 AND code != '' ORDER BY idx",
                self.rev,
                d,
            )
            if not heads:
                return NavigateResult(revision=self.rev, found=False, message=f"Chapter {d} not found")
            notes = [n for n in (self._note_excerpt("chapter", d),) if n]
            sec = heads[0]["section"]
            sn = self._note_excerpt("section", sec)
            if sn:
                notes.insert(0, sn)
            return NavigateResult(
                revision=self.rev,
                found=True,
                children=[self._row_to_node(h) for h in heads],
                notes=notes,
                message=f"Chapter {d} headings",
            )
        row = self._find_row(d)
        if not row:
            return NavigateResult(
                revision=self.rev, found=False, message=f"{format_code(d)} is not in the {self.rev} HTS"
            )
        parent = None
        p = row["parent_idx"]
        while p >= 0:
            pr = self._q("SELECT * FROM hts_rows WHERE rev=? AND idx=?", self.rev, p)[0]
            if pr["code"]:
                parent = self._row_to_node(pr)
                break
            p = pr["parent_idx"]
        kids = [self._row_to_node(c) for c in self._numbered_children(self.rev, row["idx"])]
        notes = [
            n
            for n in (
                self._note_excerpt("section", row["section"]),
                self._note_excerpt("chapter", row["chapter"]),
            )
            if n
        ]
        return NavigateResult(
            revision=self.rev,
            found=True,
            node=self._row_to_node(row),
            parent=parent,
            children=kids,
            notes=notes,
        )

    def hts_search(self, text: str, limit: int = 10) -> HtsSearchResult:
        limit = max(1, min(limit, 25))
        hits = self.search.search_hts(text, k=limit)
        out = []
        for h in hits:
            r = self._q("SELECT * FROM hts_rows WHERE rev=? AND idx=?", self.rev, int(h.key))
            if not r:
                continue
            r = r[0]
            out.append(
                HtsSearchHit(
                    code=r["code"],
                    description=r["description"],
                    path=r["path"][-600:],
                    level=_level(r["digits"]),
                    score=round(h.score, 5),
                )
            )
        return HtsSearchResult(revision=self.rev, query=text, hits=out)

    def get_notes(self, scope: str, id: str, offset: int = 0) -> NotesResult:
        scope = scope.lower().strip()
        nid = id.strip()
        if scope == "chapter":
            nid = digits(nid).zfill(2)[:2]
        elif scope == "section":
            nid = nid.upper().replace("SECTION", "").strip()
            if nid.isdigit():
                nid = SECTIONS[int(nid) - 1][0] if 1 <= int(nid) <= len(SECTIONS) else nid
        else:
            return NotesResult(revision=self.rev, scope="chapter", id=nid, title="", found=False)
        rows = self._q("SELECT title, text FROM notes WHERE rev=? AND scope=? AND id=?", self.rev, scope, nid)
        if not rows:
            return NotesResult(revision=self.rev, scope=scope, id=nid, title="", found=False)
        return NotesResult(
            revision=self.rev,
            scope=scope,
            id=nid,
            title=rows[0]["title"],
            found=True,
            text=wrap(f"HTS {scope} {nid} notes", rows[0]["text"], self.limit, offset),
        )

    def get_gri(self) -> GriResult:
        rows = self._q("SELECT text FROM notes WHERE rev=? AND scope='gri'", self.rev)
        text = rows[0]["text"] if rows else ""
        return GriResult(
            revision=self.rev,
            text=wrap("HTS General Rules of Interpretation", text, 20000),
            summary=GRI_SUMMARY,
        )

    def cross_search(
        self, query: str, date_from: str | None = None, date_to: str | None = None, limit: int = 8
    ) -> CrossSearchResult:
        limit = max(1, min(limit, 20))
        hits = self.search.search_rulings(
            query, k=limit, date_from=date_from or None, date_to=date_to or None, exclude=self.redacted
        )
        out = []
        for h in hits:
            r = self._ruling_row(h.key)
            if not r:
                continue
            st = self._status(r["id"])
            out.append(
                RulingHit(
                    id=r["id"],
                    date=r["date"] or "",
                    collection=r["collection"] or "",
                    subject=(r["subject"] or "")[:300],
                    codes=json.loads(r["tariffs"] or "[]")[:10],
                    status=st["status"],
                    snippet=wrap(f"CBP CROSS ruling {r['id']}", best_snippet(r["text"] or "", query), 600),
                    score=round(h.score, 5),
                )
            )
        return CrossSearchResult(query=query, hits=out)

    def get_ruling(self, id: str, offset: int = 0) -> RulingResult:
        r = self._ruling_row(id)
        if not r:
            return RulingResult(id=id, found=False, message="Ruling not found in the corpus")
        st = self._status(r["id"])
        return RulingResult(
            id=r["id"],
            found=True,
            date=r["date"] or "",
            collection=r["collection"] or "",
            subject=r["subject"] or "",
            codes=json.loads(r["tariffs"] or "[]"),
            status=st["status"],
            text=wrap(f"CBP CROSS ruling {r['id']}", r["text"] or "", self.limit, offset),
        )

    def ruling_status(self, id: str) -> RulingStatusResult:
        r = self._ruling_row(id)
        if not r:
            return RulingStatusResult(id=id, status="unknown", method="not_in_corpus")
        st = self._status(r["id"])
        return RulingStatusResult(
            id=r["id"], status=st["status"], linked_rulings=st["linked"], method=st["method"]
        )

    def revisions(self) -> list[str]:
        return [r["name"] for r in self._q("SELECT name FROM revisions ORDER BY year, name")]

    def _resolve_rev(self, rev: str) -> str | None:
        rev = (rev or "").strip()
        names = self.revisions()
        if rev.lower() in ("", "current", "latest"):
            return self.rev
        if rev in names:
            return rev
        if rev.isdigit():
            cands = [n for n in names if n.startswith(rev)]
            return cands[0] if cands else None
        return None

    def hts_revision_diff(self, code: str, rev_a: str, rev_b: str = "current") -> RevisionDiffResult:
        ra, rb = self._resolve_rev(rev_a), self._resolve_rev(rev_b)
        avail = self.revisions()
        if not ra or not rb:
            return RevisionDiffResult(
                code=code,
                rev_a=rev_a,
                rev_b=rev_b,
                change="not_found",
                details=["Unknown revision"],
                available_revisions=avail,
            )
        a, b = self._find_row(code, ra), self._find_row(code, rb)
        na = self._row_to_node(a) if a else None
        nb = self._row_to_node(b) if b else None
        details = []
        if not a and not b:
            change = "not_found"
        elif not a:
            change = "added"
        elif not b:
            change = "removed"
            # Show where the old line's siblings went.
            d = digits(code)
            for prefix in (d[:6], d[:4]):
                near = self._q(
                    "SELECT code, path FROM hts_rows WHERE rev=? AND digits LIKE ? AND length(digits)=10 LIMIT 8",
                    rb,
                    prefix + "%",
                )
                if near:
                    details = [f"now under {prefix}: {n['code']} {n['path'][-160:]}" for n in near]
                    break
        elif na.path != nb.path:
            change = "description_changed"
            details = [f"{ra}: {na.path}", f"{rb}: {nb.path}"]
        elif (na.general_rate, na.other_rate) != (nb.general_rate, nb.other_rate):
            change = "rate_changed"
            details = [f"{ra} general {na.general_rate}", f"{rb} general {nb.general_rate}"]
        else:
            change = "unchanged"
        return RevisionDiffResult(
            code=format_code(digits(code)),
            rev_a=ra,
            rev_b=rb,
            change=change,
            node_a=na,
            node_b=nb,
            details=details,
            available_revisions=avail,
        )


_tools: TariffTools | None = None


def get_tools() -> TariffTools:
    global _tools
    if _tools is None:
        _tools = TariffTools()
    return _tools
