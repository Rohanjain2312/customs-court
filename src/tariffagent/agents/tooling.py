"""Expose the MCP tool implementation to model tool use, with events and truncation.

The agents call the same TariffTools object the MCP server wraps, so eval runs,
the demo and MCP clients all see identical tool behavior.
"""

from __future__ import annotations

import json
import re
import time

from pydantic import BaseModel

from tariffagent.agents.events import EventBus, ToolCall, TreeFocus
from tariffagent.llm.base import ToolSpec
from tariffagent.mcp_server.tools.core import TariffTools

MAX_TOOL_CHARS = 6000


def _s(desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        "hts_search",
        "Find candidate HTS headings and subheadings for product words (keyword plus semantic search).",
        _s(
            "",
            {"text": {"type": "string"}, "limit": {"type": "integer", "description": "1 to 25, default 8"}},
            ["text"],
        ),
    ),
    ToolSpec(
        "hts_navigate",
        "Show an HTS node (chapter '42', heading '4202', subheading '4202.21', or full code) with parent, children, rates and note excerpts.",
        _s("", {"code": {"type": "string"}}, ["code"]),
    ),
    ToolSpec(
        "get_notes",
        "Full section or chapter notes, including exclusions. scope is 'section' or 'chapter'; id is like '42' or 'XVI'. Use offset to page.",
        _s(
            "",
            {
                "scope": {"type": "string", "enum": ["section", "chapter"]},
                "id": {"type": "string"},
                "offset": {"type": "integer"},
            },
            ["scope", "id"],
        ),
    ),
    ToolSpec("get_gri", "The General Rules of Interpretation, full legal text.", _s("", {}, [])),
    ToolSpec(
        "cross_search",
        "Search CBP CROSS rulings. Each hit has id, date, codes, status and a snippet.",
        _s(
            "",
            {
                "query": {"type": "string"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "1 to 20, default 6"},
            },
            ["query"],
        ),
    ),
    ToolSpec(
        "get_ruling",
        "Full text of one CROSS ruling with its codes and status. Use offset to page long rulings.",
        _s("", {"id": {"type": "string"}, "offset": {"type": "integer"}}, ["id"]),
    ),
    ToolSpec(
        "ruling_status",
        "Whether a ruling is in_force, modified or revoked, and which rulings changed it.",
        _s("", {"id": {"type": "string"}}, ["id"]),
    ),
    ToolSpec(
        "hts_revision_diff",
        "Compare one HTS line between an older revision (a year like '2019') and the current one.",
        _s(
            "",
            {"code": {"type": "string"}, "rev_a": {"type": "string"}, "rev_b": {"type": "string"}},
            ["code", "rev_a"],
        ),
    ),
]
TOOL_NAMES = {t.name for t in TOOL_SPECS}


def compact(model: BaseModel) -> str:
    """Serialize a tool result compactly and cap its size."""
    d = model.model_dump(mode="json", exclude_defaults=False)
    s = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    if len(s) > MAX_TOOL_CHARS:
        s = s[:MAX_TOOL_CHARS] + '..."[truncated: call again with offset or a narrower query]'
    return s


class InProcessBackend:
    """Calls the shared TariffTools implementation directly."""

    def __init__(self, tools: TariffTools):
        self.tools = tools

    def call(self, name: str, args: dict) -> str:
        fn = getattr(self.tools, name)
        if name == "hts_search":
            res = fn(args.get("text", ""), int(args.get("limit") or 8))
        elif name == "cross_search":
            res = fn(
                args.get("query", ""), args.get("date_from"), args.get("date_to"), int(args.get("limit") or 6)
            )
        elif name == "get_notes":
            res = fn(args.get("scope", "chapter"), str(args.get("id", "")), int(args.get("offset") or 0))
        elif name == "get_ruling":
            res = fn(str(args.get("id", "")), int(args.get("offset") or 0))
        elif name == "hts_revision_diff":
            res = fn(
                str(args.get("code", "")), str(args.get("rev_a", "")), str(args.get("rev_b") or "current")
            )
        elif name == "get_gri":
            res = fn()
        else:
            res = fn(**args)
        return compact(res)


class MCPBackend:
    """Calls the tools through a real MCP client session (stdio or HTTP).

    Runs the async client on a private event loop thread so the sync agent loop can use it.
    """

    def __init__(self, server):
        import asyncio
        import threading

        from mcp import Client

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._client = None
        self._error: BaseException | None = None

        async def hold():
            # Enter and exit the client in one task, as anyio requires.
            self._stop = asyncio.Event()
            try:
                async with Client(server) as c:
                    self._client = c
                    self._ready.set()
                    await self._stop.wait()
            except BaseException as e:  # noqa: BLE001
                self._error = e
                self._ready.set()

        self._holder = asyncio.run_coroutine_threadsafe(hold(), self._loop)
        self._ready.wait(timeout=60)
        if self._error or self._client is None:
            raise RuntimeError(f"MCP client failed to start: {self._error}")

    def _run(self, coro):
        import asyncio

        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=120)

    def list_tools(self) -> list[str]:
        return [t.name for t in self._run(self._client.list_tools()).tools]

    def call(self, name: str, args: dict) -> str:
        clean = {k: v for k, v in args.items() if v is not None}
        res = self._run(self._client.call_tool(name, clean))
        if res.is_error:
            raise RuntimeError("".join(getattr(c, "text", "") for c in res.content)[:500])
        s = json.dumps(res.structured_content, ensure_ascii=False, separators=(",", ":"))
        if len(s) > MAX_TOOL_CHARS:
            s = s[:MAX_TOOL_CHARS] + '..."[truncated: call again with offset or a narrower query]'
        return s

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._stop.set)
            self._holder.result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)


class ToolExecutor:
    def __init__(
        self, backend, bus: EventBus | None = None, agent: str = "single", allowed: set[str] | None = None
    ):
        self.backend = backend if hasattr(backend, "call") else InProcessBackend(backend)
        self.bus = bus
        self.agent = agent
        self.allowed = allowed or TOOL_NAMES
        self.calls = 0

    def run(self, name: str, args: dict) -> tuple[str, bool]:
        """Returns (result text, is_error)."""
        self.calls += 1
        t0 = time.perf_counter()
        try:
            if name not in self.allowed:
                raise ValueError(f"Unknown or disallowed tool {name}")
            out, err = self.backend.call(name, args), False
        except Exception as e:  # noqa: BLE001
            out, err = f"Tool error: {e}", True
        ms = int((time.perf_counter() - t0) * 1000)
        if self.bus:
            self.bus.emit(ToolCall(agent=self.agent, tool=name, args=args, result_preview=out[:300], ms=ms))
            code = args.get("code") if name in ("hts_navigate", "hts_revision_diff") else None
            if code and re.sub(r"\D", "", code):
                self.bus.emit(TreeFocus(agent=self.agent, code=code, state="visited"))
            if name == "hts_search" and not err and out.endswith("}"):
                for h in json.loads(out).get("hits", [])[:5]:
                    self.bus.emit(TreeFocus(agent=self.agent, code=h["code"], state="candidate"))
        return out, err
