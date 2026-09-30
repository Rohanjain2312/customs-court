"""Hybrid retrieval: SQLite FTS5 (BM25) plus a local embedding index, fused with RRF.

Embeddings use BAAI/bge-small-en-v1.5 run locally through sentence-transformers.
No paid embedding API is used.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tariffagent.config import get_settings
from tariffagent.data.db import connect
from tariffagent.data.hts import current_rev

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RRF_K = 60

_model = None
_model_lock = threading.Lock()
# The embedding model and the vector indexes are not safe to use from several threads at once
# (a silent crash with TOOLS_PARALLEL=true), so each query's embed + vector search is serialized.
# The SQLite and FTS parts stay parallel.
_vec_lock = threading.Lock()


def index_dir() -> Path:
    p = get_settings().data_dir / "index"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "mps" if torch.backends.mps.is_available() else "cpu"
            _model = SentenceTransformer(EMBED_MODEL, device=device)
    return _model


def embed(texts: list[str], batch_size: int = 64, query: bool = False) -> np.ndarray:
    m = get_model()
    if query:
        texts = [QUERY_PREFIX + t for t in texts]
    v = m.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 1000)
    return np.asarray(v, dtype=np.float32)


def ruling_doc(subject: str, text: str) -> str:
    return f"{subject or ''}\n{(text or '')[:1800]}"


def build_fts(con: sqlite3.Connection | None = None) -> dict:
    con = con or connect()
    rev = current_rev(con)
    con.executescript(
        """
        DROP TABLE IF EXISTS rulings_fts;
        CREATE VIRTUAL TABLE rulings_fts USING fts5(id UNINDEXED, subject, body, codes, tokenize='porter unicode61');
        DROP TABLE IF EXISTS hts_fts;
        CREATE VIRTUAL TABLE hts_fts USING fts5(idx UNINDEXED, code, description, path, tokenize='porter unicode61');
        """
    )
    con.execute(
        "INSERT INTO rulings_fts (id, subject, body, codes) "
        "SELECT id, subject, substr(text, 1, 20000), tariffs FROM rulings WHERE text IS NOT NULL AND text != ''"
    )
    con.execute(
        "INSERT INTO hts_fts (idx, code, description, path) "
        "SELECT idx, code, description, path FROM hts_rows WHERE rev=? AND code != ''",
        (rev,),
    )
    con.commit()
    n1 = con.execute("SELECT COUNT(*) FROM rulings_fts").fetchone()[0]
    n2 = con.execute("SELECT COUNT(*) FROM hts_fts").fetchone()[0]
    return {"rulings_fts": n1, "hts_fts": n2}


def build_embeddings(
    con: sqlite3.Connection | None = None, which: tuple[str, ...] = ("rulings", "hts")
) -> dict:
    con = con or connect()
    out = {}
    if "rulings" in which:
        rows = con.execute(
            "SELECT id, subject, text FROM rulings WHERE text IS NOT NULL AND text != '' ORDER BY id"
        ).fetchall()
        # Incremental: reuse vectors for ids already embedded with the same document.
        import hashlib

        old_vecs, old_ids, old_h = None, [], []
        vp, ip, hp = (
            index_dir() / "rulings.npy",
            index_dir() / "rulings_ids.json",
            index_dir() / "rulings_hash.json",
        )
        if vp.exists() and ip.exists() and hp.exists():
            old_vecs = np.load(vp)
            old_ids = json.loads(ip.read_text())
            old_h = json.loads(hp.read_text())
        old = {i: (k, h) for k, (i, h) in enumerate(zip(old_ids, old_h, strict=True))}
        docs = [ruling_doc(r["subject"], r["text"]) for r in rows]
        hashes = [hashlib.sha1(d.encode()).hexdigest()[:16] for d in docs]
        need = [k for k, r in enumerate(rows) if r["id"] not in old or old[r["id"]][1] != hashes[k]]
        new_vecs = embed([docs[k] for k in need]) if need else np.zeros((0, 384), dtype=np.float32)
        out_vecs = np.zeros((len(rows), 384), dtype=np.float16)
        nk = 0
        for k, r in enumerate(rows):
            if need and nk < len(need) and need[nk] == k:
                out_vecs[k] = new_vecs[nk]
                nk += 1
            else:
                out_vecs[k] = old_vecs[old[r["id"]][0]]
        np.save(vp, out_vecs)
        ip.write_text(json.dumps([r["id"] for r in rows]))
        hp.write_text(json.dumps(hashes))
        out["rulings"] = len(rows)
        out["rulings_newly_embedded"] = len(need)
    if "hts" in which:
        rev = current_rev(con)
        rows = con.execute(
            "SELECT idx, code, path FROM hts_rows WHERE rev=? AND code != '' ORDER BY idx", (rev,)
        ).fetchall()
        vecs = embed([f"{r['code']} {r['path'][-700:]}" for r in rows])
        np.save(index_dir() / "hts.npy", vecs.astype(np.float16))
        (index_dir() / "hts_idx.json").write_text(json.dumps([r["idx"] for r in rows]))
        out["hts"] = len(rows)
    return out


_TOKEN = re.compile(r"[A-Za-z0-9]+")


def fts_query(text: str) -> str:
    toks = [t for t in _TOKEN.findall(text) if len(t) > 1][:40]
    return " OR ".join(f'"{t}"' for t in toks) if toks else '""'


@dataclass
class Hit:
    key: str
    score: float
    bm25_rank: int | None
    vec_rank: int | None


class VectorIndex:
    def __init__(self, name: str):
        self.name = name
        self._vecs: np.ndarray | None = None
        self._keys: list | None = None

    def load(self):
        if self._vecs is None:
            p = index_dir() / f"{self.name}.npy"
            keys = index_dir() / ("rulings_ids.json" if self.name == "rulings" else "hts_idx.json")
            if not p.exists():
                return None, None
            self._vecs = np.load(p).astype(np.float32)
            self._keys = json.loads(keys.read_text())
        return self._vecs, self._keys

    def search(self, qv: np.ndarray, k: int, allow=None) -> list[tuple]:
        vecs, keys = self.load()
        if vecs is None:
            return []
        sims = vecs @ qv
        order = np.argsort(-sims)
        out = []
        for i in order:
            key = keys[i]
            if allow is not None and not allow(key):
                continue
            out.append((key, float(sims[i])))
            if len(out) >= k:
                break
        return out


def rrf(bm25: list, vec: list, k: int) -> list[Hit]:
    scores: dict = {}
    ranks: dict = {}
    for r, key in enumerate(bm25):
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + r + 1)
        ranks.setdefault(key, [None, None])[0] = r + 1
    for r, key in enumerate(vec):
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + r + 1)
        ranks.setdefault(key, [None, None])[1] = r + 1
    items = sorted(scores.items(), key=lambda x: -x[1])[:k]
    return [Hit(str(key), s, ranks[key][0], ranks[key][1]) for key, s in items]


class HybridSearch:
    """Search rulings and HTS lines. Calls are serialized with a lock: the SQLite
    connection and the embedding model (MPS) are not safe to share across threads."""

    def __init__(self, con: sqlite3.Connection | None = None, use_vectors: bool = True):
        self.con = con or connect()
        self._lock = threading.RLock()
        self.use_vectors = use_vectors
        self.rulings_vi = VectorIndex("rulings")
        self.hts_vi = VectorIndex("hts")

    def search_rulings(self, *a, **kw) -> list[Hit]:
        with self._lock:
            return self._search_rulings(*a, **kw)

    def search_hts(self, *a, **kw) -> list[Hit]:
        with self._lock:
            return self._search_hts(*a, **kw)

    def _search_rulings(
        self,
        query: str,
        k: int = 10,
        date_from: str | None = None,
        date_to: str | None = None,
        exclude: set[str] | None = None,
        pool: int = 60,
    ) -> list[Hit]:
        exclude = exclude or set()
        meta = {}

        def allowed(rid: str) -> bool:
            if rid in exclude:
                return False
            if date_from or date_to:
                if rid not in meta:
                    row = self.con.execute("SELECT date FROM rulings WHERE id=?", (rid,)).fetchone()
                    meta[rid] = row["date"] if row else ""
                d = meta[rid] or ""
                if date_from and d < date_from:
                    return False
                if date_to and d > date_to:
                    return False
            return True

        bm = []
        for r in self.con.execute(
            "SELECT id FROM rulings_fts WHERE rulings_fts MATCH ? ORDER BY bm25(rulings_fts, 0, 4.0, 1.0, 2.0) LIMIT ?",
            (fts_query(query), pool * 4),
        ):
            if allowed(r["id"]):
                bm.append(r["id"])
            if len(bm) >= pool:
                break
        vec = []
        if self.use_vectors:
            with _vec_lock:
                qv = embed([query], query=True)[0]
                vec = [key for key, _ in self.rulings_vi.search(qv, pool, allow=allowed)]
        return rrf(bm, vec, k)

    def _special_idx(self) -> set[int]:
        """Chapters 98 and 99 (special provisions, temporary and additional duties) are never the
        product classification, and their long descriptions crowd out real headings in search."""
        if not hasattr(self, "_special"):
            rev = current_rev(self.con)
            self._special = {
                r[0]
                for r in self.con.execute(
                    "SELECT idx FROM hts_rows WHERE rev=? AND chapter IN ('98','99')", (rev,)
                )
            }
        return self._special

    def _search_hts(self, query: str, k: int = 10, pool: int = 60) -> list[Hit]:
        special = self._special_idx()
        bm = [
            r["idx"]
            for r in self.con.execute(
                "SELECT idx FROM hts_fts WHERE hts_fts MATCH ? ORDER BY bm25(hts_fts, 0, 1.0, 3.0, 1.0) LIMIT ?",
                (fts_query(query), pool * 3),
            )
            if int(r["idx"]) not in special
        ][:pool]
        vec = []
        if self.use_vectors:
            with _vec_lock:
                qv = embed([query], query=True)[0]
                vec = [key for key, _ in self.hts_vi.search(qv, pool, allow=lambda i: int(i) not in special)]
        return rrf(bm, vec, k)
