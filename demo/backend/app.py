"""Customs Court demo backend.

Replay mode (the default) streams recorded hearings from demo/replays with compressed
timing. It needs no API key, no network and spends nothing. Live mode runs the real
agents; it is on only when DEMO_MODE=live and ANTHROPIC_API_KEY is set, and each
browser session is capped at DEMO_SESSION_CAP_USD (default $2).

Run from the repo root:
    uv run --extra demo python -m uvicorn demo.backend.app:app --port 8765
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from demo.backend import hts_tree
from demo.backend.live import (
    Sessions,
    make_guarded_complete,
    photo_request,
    run_hearing,
    session_spent,
)
from demo.backend.replays import MAX_GAP_S, ReplayStore, reveal, schedule
from tariffagent.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
COOKIE = "cc_session"
TIMING_NOTE = (
    "Replay timing is compressed: gaps longer than {gap:g} s are cut and long text is streamed at "
    "reading pace. Tokens and dollars are as recorded."
)


class ClassifyBody(BaseModel):
    description: str = Field(min_length=8, max_length=2500)
    arm: str = "single"


class ObjectionBody(BaseModel):
    exhibit_id: str
    fact_change: str = ""
    description: str = ""


class PhotoBody(BaseModel):
    image: str = Field(max_length=7_000_000)


def _sse(ev: dict) -> str:
    return f"event: {ev.get('type', 'message')}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"


def create_app(
    mode: str | None = None,
    replay_dir: Path | None = None,
    dist_dir: Path | None = None,
    complete: Callable | None = None,
) -> FastAPI:
    """`complete` replaces the model provider in live runs (tests only)."""
    settings = get_settings()
    mode = (mode or os.environ.get("DEMO_MODE") or "replay").strip().lower()
    replay_dir = Path(replay_dir or os.environ.get("DEMO_REPLAY_DIR") or ROOT / "demo" / "replays")
    dist_dir = Path(dist_dir or os.environ.get("DEMO_FRONTEND_DIST") or ROOT / "demo" / "frontend" / "dist")
    max_gap = float(os.environ.get("DEMO_MAX_GAP_S") or MAX_GAP_S)
    cap = float(settings.demo_session_cap_usd)
    has_key = bool(settings.anthropic_api_key)
    live_enabled = mode == "live" and has_key
    if mode != "live":
        live_reason = "Replay mode. Set DEMO_MODE=live and ANTHROPIC_API_KEY to hear new exhibits."
    elif not has_key:
        live_reason = "DEMO_MODE=live is set, but ANTHROPIC_API_KEY is not. The court stays in replay mode."
    else:
        live_reason = ""

    app = FastAPI(title="Customs Court", version="1.0")
    store = ReplayStore(replay_dir)
    sessions = Sessions()
    state: dict = {"tree_tools": None, "live_tools": None}
    tools_lock = threading.Lock()

    def tree_tools():
        with tools_lock:
            if state["tree_tools"] is None:
                from tariffagent.mcp_server.tools.core import TariffTools

                if not settings.db_path.exists():
                    raise HTTPException(503, f"HTS database not found at {settings.db_path}")
                state["tree_tools"] = TariffTools(use_vectors=False, redact_eval=False)
            return state["tree_tools"]

    def live_tools():
        with tools_lock:
            if state["live_tools"] is None:
                from tariffagent.mcp_server.tools.core import TariffTools

                state["live_tools"] = TariffTools()
            return state["live_tools"]

    def session_of(request: Request):
        return sessions.get(request.cookies.get(COOKIE))

    def with_cookie(resp, sess):
        resp.set_cookie(COOKIE, sess.sid, httponly=True, samesite="lax")
        return resp

    def require_live(sess):
        if not live_enabled:
            raise HTTPException(403, live_reason)
        if session_spent(sess) >= cap:
            raise HTTPException(402, f"This session has used its ${cap:.2f} live budget.")

    # ---------- basics ----------
    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": "live" if live_enabled else "replay",
            "exhibits": len(store.items),
            "db": settings.db_path.exists(),
            "frontend_built": (dist_dir / "index.html").exists(),
        }

    @app.get("/api/config")
    def config(request: Request):
        sess = session_of(request)
        body = {
            "mode": "live" if live_enabled else "replay",
            "live": live_enabled,
            "live_reason": live_reason,
            "photo": live_enabled,
            "session_cap_usd": cap,
            "session_spent_usd": round(session_spent(sess), 6) if live_enabled else 0.0,
            "max_gap_s": max_gap,
            "timing_note": TIMING_NOTE.format(gap=max_gap),
        }
        return with_cookie(JSONResponse(body), sess)

    # ---------- replays ----------
    @app.get("/api/exhibits")
    def exhibits():
        return store.listing()

    @app.get("/api/exhibits/{exhibit_id}/reveal")
    def exhibit_reveal(exhibit_id: str):
        r = store.get(exhibit_id)
        if not r:
            raise HTTPException(404, f"No exhibit {exhibit_id}")
        if not r.meta.get("gold_code"):
            raise HTTPException(404, "No reference ruling is on file for this exhibit.")
        return reveal(r.meta)

    @app.get("/api/replay/{exhibit_id}")
    async def replay(
        exhibit_id: str,
        speed: float = Query(1.0, ge=0.0, le=50.0, description="0 sends everything at once"),
    ):
        r = store.get(exhibit_id)
        if not r:
            raise HTTPException(404, f"No recorded hearing for exhibit {exhibit_id}")
        plan = schedule(r.events(), max_gap=max_gap)

        async def gen() -> AsyncIterator[str]:
            for delay, ev in plan:
                if speed > 0 and delay > 0:
                    await asyncio.sleep(delay / speed)
                yield _sse(ev)
            yield _sse({"type": "done", "exhibit_id": exhibit_id, "replay": True})

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/objection")
    def objection(body: ObjectionBody, request: Request):
        base = store.get(body.exhibit_id)
        if live_enabled:
            fact = body.fact_change.strip()
            if len(fact) < 4:
                raise HTTPException(400, "State the one fact you want to change.")
            desc = (base.meta.get("description") if base else "") or body.description
            if not desc:
                raise HTTPException(400, "No description to object to.")
            return {
                "mode": "live",
                "fact_change": fact,
                "description": f"{desc}\n\nCorrection to the facts, which overrides anything above: {fact}",
            }
        rec = store.objection_for(body.exhibit_id)
        if not rec:
            raise HTTPException(
                404,
                "No objection is on file for this exhibit. In replay mode the court can only rehear "
                "recorded objections.",
            )
        return {
            "mode": "replay",
            "exhibit_id": rec.exhibit_id,
            "fact_change": rec.meta.get("fact_change", ""),
            "placeholder": bool(rec.meta.get("placeholder")),
        }

    # ---------- live ----------
    @app.post("/api/classify")
    async def classify(body: ClassifyBody, request: Request):
        sess = session_of(request)
        require_live(sess)
        if body.arm not in ("single", "multi"):
            raise HTTPException(400, "arm must be 'single' or 'multi'")
        with sess.lock:
            if sess.active:
                raise HTTPException(409, "A hearing is already running in this session.")
            sess.active = True
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        cancel = threading.Event()
        guarded = make_guarded_complete(sess, cap, cancel, complete)

        def emit(ev: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ev)

        def work() -> None:
            try:
                res = run_hearing(
                    description=body.description.strip(),
                    arm=body.arm,
                    sess=sess,
                    tools=live_tools(),
                    guarded=guarded,
                    emit=emit,
                )
            except Exception as e:  # noqa: BLE001
                emit({"type": "error", "t": 0.0, "run_id": "", "agent": "court", "message": str(e)[:400]})
                res = {"error": str(e)}
            finally:
                with sess.lock:
                    sess.active = False
            emit(
                {
                    "type": "done",
                    "live": True,
                    "usd": (res or {}).get("usd", 0.0),
                    "session_spent_usd": round(session_spent(sess), 6),
                    "session_cap_usd": cap,
                }
            )

        threading.Thread(target=work, daemon=True).start()

        async def gen() -> AsyncIterator[str]:
            try:
                while True:
                    try:
                        ev = await asyncio.wait_for(queue.get(), timeout=10)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield _sse(ev)
                    if ev.get("type") == "done":
                        break
            finally:
                cancel.set()

        return with_cookie(
            StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}),
            sess,
        )

    @app.post("/api/describe-photo")
    def describe_photo(body: PhotoBody, request: Request):
        sess = session_of(request)
        require_live(sess)
        try:
            req = photo_request(body.image, settings.advocate_model)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        guarded = make_guarded_complete(sess, cap, threading.Event(), complete)
        try:
            resp = guarded(req)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"The photo could not be described: {str(e)[:300]}") from e
        return with_cookie(
            JSONResponse(
                {"description": resp.text.strip(), "session_spent_usd": round(session_spent(sess), 6)}
            ),
            sess,
        )

    # ---------- HTS ----------
    @app.get("/api/hts/{code}")
    def hts(code: str):
        n = hts_tree.node(tree_tools(), code)
        if not n:
            raise HTTPException(404, f"{code} is not in the current HTS")
        return n

    @app.get("/api/revisions")
    def revisions():
        t = tree_tools()
        rows = t._q("SELECT name, year FROM revisions ORDER BY year, name")
        return {
            "current": t.rev,
            "revisions": [{"name": r["name"], "year": r["year"]} for r in rows],
        }

    @app.get("/api/hts-diff")
    def hts_diff(code: str, rev_a: str, rev_b: str = "current"):
        res = tree_tools().hts_revision_diff(code, rev_a, rev_b)
        return res.model_dump(mode="json")

    # ---------- frontend ----------
    if (dist_dir / "index.html").exists():
        if (dist_dir / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            f = (dist_dir / path).resolve()
            if path and f.is_file() and dist_dir.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist_dir / "index.html")

    else:

        @app.get("/", include_in_schema=False)
        def not_built():
            return HTMLResponse(
                "<h1>Customs Court</h1><p>The frontend is not built. Run <code>make replay</code>, "
                "or <code>cd demo/frontend && npm run build</code>.</p>",
                status_code=503,
            )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app


app = create_app()
