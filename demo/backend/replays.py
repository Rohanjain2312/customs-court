"""Recorded hearings: load replay files and schedule their events for streaming.

Replay file format (see demo/replays/README.md): the first line is a metadata object
with "type": "meta", then one typed agent event per line in recorded order.

Recorded timestamps come from eval runs. Batch runs have gaps of minutes while a
batch waits, and cached calls have none, so the stream is re-timed: every gap is
capped, a few event types get a short minimum gap so the tree and cards can animate,
and long text chunks are split into short pieces so they appear to stream. The
concatenated text of the pieces equals the recorded text.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from tariffagent.agents.events import EventAdapter

log = logging.getLogger("customs_court.replays")

# Fields of a mystery exhibit that stay sealed until the reveal.
SEALED = ("gold_code", "gold_digits", "ruling_id", "ruling_date", "reference_excerpt", "outcome")

MAX_GAP_S = 1.5
MIN_GAP_S = {
    "run_start": 0.0,
    "tool_call": 0.45,
    "tree_focus": 0.16,
    "fact_extracted": 0.4,
    "advocate_done": 0.35,
    "ruling": 0.7,
    "cost_update": 0.05,
}
PIECE_CHARS = 28  # characters per streamed piece of a long text chunk
PIECE_GAP_S = 0.045
MAX_CHUNK_S = 3.0  # a single recorded chunk never takes longer than this to stream


@dataclass
class Replay:
    path: Path
    meta: dict
    _events: list[dict] | None = field(default=None, repr=False)

    @property
    def exhibit_id(self) -> str:
        return self.meta["exhibit_id"]

    def events(self) -> list[dict]:
        if self._events is None:
            out = []
            with self.path.open() as f:
                next(f, None)  # metadata line
                for i, line in enumerate(f, start=2):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = EventAdapter.validate_python(json.loads(line))
                    except Exception as e:  # noqa: BLE001
                        log.warning("skipping invalid event %s:%d: %s", self.path.name, i, e)
                        continue
                    out.append(ev.model_dump())
            self._events = out
        return self._events


class ReplayStore:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.items: dict[str, Replay] = {}
        self.reload()

    def reload(self) -> None:
        self.items = {}
        if not self.dir.exists():
            return
        for p in sorted(self.dir.glob("*.jsonl")):
            try:
                with p.open() as f:
                    meta = json.loads(f.readline())
            except Exception as e:  # noqa: BLE001
                log.warning("skipping %s: %s", p.name, e)
                continue
            if meta.get("type") != "meta" or not meta.get("exhibit_id"):
                log.warning("skipping %s: first line is not replay metadata", p.name)
                continue
            self.items[meta["exhibit_id"]] = Replay(p, meta)

    def get(self, exhibit_id: str) -> Replay | None:
        return self.items.get(exhibit_id)

    def listing(self) -> list[dict]:
        """Public metadata for every replay, with sealed fields removed and links filled in."""
        metas = [r.meta for r in self.items.values()]
        by_pair: dict[str, dict[str, str]] = {}
        for m in metas:
            if m.get("kind") == "objection":
                continue
            by_pair.setdefault(m.get("pair") or m["exhibit_id"], {}).setdefault(
                m.get("agent", "single"), m["exhibit_id"]
            )
        out = []
        for m in sorted(metas, key=lambda m: (m.get("order", 999), m["exhibit_id"])):
            pub = public_meta(m)
            if m.get("kind") != "objection":
                pub["arms"] = by_pair.get(m.get("pair") or m["exhibit_id"], {})
            pub["objections"] = [o["exhibit_id"] for o in metas if o.get("objection_of") == m["exhibit_id"]]
            out.append(pub)
        return out

    def objection_for(self, exhibit_id: str) -> Replay | None:
        base = self.get(exhibit_id)
        cands = [r for r in self.items.values() if r.meta.get("objection_of") == exhibit_id]
        if base and cands:
            same = [r for r in cands if r.meta.get("agent") == base.meta.get("agent")]
            return (same or cands)[0]
        return cands[0] if cands else None


def public_meta(meta: dict) -> dict:
    m = {k: v for k, v in meta.items() if k != "type"}
    if m.get("mystery"):
        for k in SEALED:
            m.pop(k, None)
        m["sealed"] = True
    return m


def reveal(meta: dict) -> dict:
    return {
        "exhibit_id": meta["exhibit_id"],
        "gold_code": meta.get("gold_code") or "",
        "ruling_id": meta.get("ruling_id") or "",
        "ruling_date": meta.get("ruling_date") or "",
        "reference_excerpt": meta.get("reference_excerpt") or "",
        "dataset": (meta.get("source") or {}).get("dataset", ""),
    }


def _split_text(text: str) -> list[str]:
    if len(text) <= PIECE_CHARS * 2:
        return [text]
    size = max(PIECE_CHARS, int(len(text) / (MAX_CHUNK_S / PIECE_GAP_S)) + 1)
    pieces, i = [], 0
    while i < len(text):
        j = min(len(text), i + size)
        # End pieces on a space when one is close, so words do not break mid-way on screen.
        if j < len(text):
            k = text.rfind(" ", i + size // 2, j + 8)
            if k > i:
                j = k + 1
        pieces.append(text[i:j])
        i = j
    return pieces


def schedule(events: list[dict], max_gap: float = MAX_GAP_S) -> list[tuple[float, dict]]:
    """Returns (delay before sending, event) pairs on a compressed clock.

    Each event keeps its recorded time as t_orig; t becomes the compressed time.
    """
    out: list[tuple[float, dict]] = []
    prev_orig = None
    clock = 0.0
    for ev in events:
        t0 = float(ev.get("t") or 0.0)
        gap = 0.0 if prev_orig is None else max(0.0, t0 - prev_orig)
        prev_orig = t0
        typ = ev.get("type", "")
        delay = max(min(gap, max_gap), MIN_GAP_S.get(typ, 0.05) if out else 0.0)
        if typ in ("advocate_chunk", "adjudicator_chunk") and ev.get("text"):
            for n, piece in enumerate(_split_text(ev["text"])):
                d = delay if n == 0 else PIECE_GAP_S
                clock += d
                out.append((d, {**ev, "text": piece, "t": round(clock, 3), "t_orig": t0}))
            continue
        clock += delay
        out.append((delay, {**ev, "t": round(clock, 3), "t_orig": t0}))
    return out
