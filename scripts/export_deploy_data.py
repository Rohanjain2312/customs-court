"""Stage the data that the deploy images bake in. Deploy-ready, not deployed.

Copies the tables the MCP server reads from $DATA_DIR/tariffagent.sqlite plus the
vector index into a staging directory, switches the copy to rollback-journal mode
(so a read-only container can open it without -wal/-shm files), VACUUMs it and
prints sizes. It also writes a tiny agent database (revisions and the GRI text)
for the classifier agent image, which reads the GRI into its system prompt.

    uv run python scripts/export_deploy_data.py              # real data, $DATA_DIR
    uv run python scripts/export_deploy_data.py --fixture    # 12 MB test fixture

The source database is opened read-only and is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "data"
DEFAULT_OUT = ROOT / "deploy" / ".build"

# Tables the MCP tools read. The FTS5 shadow tables (_config, _content, _data,
# _docsize, _idx) belong to their virtual table and are kept with it.
MCP_TABLES = [
    "revisions",
    "hts_rows",
    "notes",
    "rulings",
    "ruling_status",
    "crosswalk",
    "eval_redactions",
    "rulings_fts",
    "hts_fts",
]
INDEX_FILES = ["rulings.npy", "rulings_ids.json", "rulings_hash.json", "hts.npy", "hts_idx.json"]


def _mb(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_ro(p: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=120)


def _kept(name: str) -> bool:
    return name in MCP_TABLES or any(name.startswith(t + "_") and t.endswith("_fts") for t in MCP_TABLES)


def export_mcp_db(src: Path, dst: Path) -> dict:
    """Snapshot src into dst, drop tables the tools never read, VACUUM."""
    if dst.exists():
        dst.unlink()
    con = _open_ro(src)
    # VACUUM INTO writes a consistent, compacted snapshot and works on a read-only connection.
    con.execute("VACUUM INTO ?", (str(dst),))
    con.close()
    out = sqlite3.connect(dst)
    names = [r[0] for r in out.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    missing = [t for t in MCP_TABLES if t not in names]
    if missing:
        raise SystemExit(f"source database is missing tables: {missing}")
    dropped = []
    for n in names:
        if not _kept(n) and not n.startswith("sqlite_"):
            out.execute(f'DROP TABLE IF EXISTS "{n}"')
            dropped.append(n)
    out.execute("PRAGMA journal_mode=DELETE")
    out.commit()
    out.execute("VACUUM")
    ok = out.execute("PRAGMA quick_check").fetchone()[0]
    counts = {t: out.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in MCP_TABLES}
    rev = out.execute("SELECT name FROM revisions WHERE is_current=1").fetchone()
    out.close()
    if ok != "ok":
        raise SystemExit(f"quick_check failed on {dst}: {ok}")
    return {"rows": counts, "dropped_tables": dropped, "current_revision": rev[0] if rev else None}


def export_agent_db(src_mcp_db: Path, dst: Path) -> dict:
    """The agent only needs the current revision name and the GRI text."""
    if dst.exists():
        dst.unlink()
    out = sqlite3.connect(dst)
    out.execute("PRAGMA journal_mode=DELETE")
    out.execute("ATTACH DATABASE ? AS src", (str(src_mcp_db),))
    out.execute("CREATE TABLE revisions AS SELECT * FROM src.revisions")
    out.execute("CREATE TABLE notes AS SELECT * FROM src.notes WHERE scope='gri'")
    out.commit()
    out.execute("DETACH DATABASE src")
    out.execute("VACUUM")
    n = out.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    out.close()
    if n == 0:
        raise SystemExit("no GRI notes found; the agent system prompt would be empty")
    return {"gri_rows": n}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", action="store_true", help="use tests/fixtures/data instead of $DATA_DIR")
    ap.add_argument(
        "--data-dir", type=Path, default=None, help="source data dir (default $DATA_DIR or ./data)"
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="staging root (default deploy/.build)")
    ap.add_argument("--no-index", action="store_true", help="skip the vector index (BM25-only images)")
    a = ap.parse_args(argv)

    if a.fixture:
        src_dir = FIXTURE_DIR
    else:
        src_dir = a.data_dir or Path(os.environ.get("DATA_DIR", ROOT / "data"))
    src_db = src_dir / "tariffagent.sqlite"
    if not src_db.exists():
        print(f"error: {src_db} not found", file=sys.stderr)
        return 2

    data_out = a.out / "data"
    agent_out = a.out / "agent_data"
    for d in (data_out, agent_out):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    # Always create index/ so a read-only container never tries to mkdir it.
    (data_out / "index").mkdir()

    print(f"source: {src_db} ({_mb(src_db.stat().st_size)} main file)")
    info = export_mcp_db(src_db, data_out / "tariffagent.sqlite")
    agent_info = export_agent_db(data_out / "tariffagent.sqlite", agent_out / "tariffagent.sqlite")

    copied = []
    src_index = src_dir / "index"
    if not a.no_index and src_index.is_dir():
        for name in INDEX_FILES:
            p = src_index / name
            if p.exists():
                shutil.copy2(p, data_out / "index" / name)
                copied.append(name)
    vectors = {"rulings.npy", "rulings_ids.json", "hts.npy", "hts_idx.json"} <= set(copied)

    files = {}
    for p in sorted(a.out.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files[str(p.relative_to(a.out))] = {"bytes": p.stat().st_size, "sha256": _sha256(p)}
    manifest = {
        "note": "Deploy-ready, not deployed. Staged data for the container images.",
        "source": str(src_db),
        "fixture": a.fixture,
        "has_vector_index": vectors,
        **info,
        "agent_db": agent_info,
        "files": files,
    }
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=1))

    print(f"staged into {a.out}")
    for rel, f in files.items():
        print(f"  {rel:40s} {_mb(f['bytes']):>10s}")
    total = sum(f["bytes"] for f in files.values())
    print(f"  {'total':40s} {_mb(total):>10s}")
    print(f"rows: {json.dumps(info['rows'])}")
    if info["dropped_tables"]:
        print(f"dropped tables not read by the tools: {info['dropped_tables']}")
    print(
        f"vector index staged: {vectors}"
        + ("" if vectors else " (images must run with --no-vectors or VECTORS=0)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
