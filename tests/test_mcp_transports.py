"""Call every tool over stdio and over stateless Streamable HTTP with the real SDK client."""

import json
import os
import socket
import subprocess
import sys
import time

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from tests.conftest import FIXTURE_DATA

INFO = json.loads((FIXTURE_DATA / "fixture_info.json").read_text())
EXPECTED = {
    "hts_navigate", "hts_search", "get_notes", "get_gri", "cross_search", "get_ruling", "ruling_status", "hts_revision_diff",
}
CALLS = [
    ("hts_navigate", {"code": "4202.21"}, lambda d: d["found"] and d["node"]["code"].startswith("4202.21")),
    ("hts_search", {"text": "leather handbag", "limit": 5}, lambda d: len(d["hits"]) > 0),
    ("get_notes", {"scope": "chapter", "id": "42"}, lambda d: d["found"]),
    ("get_gri", {}, lambda d: "summary" in d),
    ("cross_search", {"query": "footwear rubber sole", "limit": 3}, lambda d: "hits" in d),
    ("get_ruling", {"id": INFO["poison_id"]}, lambda d: d["found"] and d["text"]["kind"] == "untrusted_corpus_text"),
    ("ruling_status", {"id": INFO["poison_id"]}, lambda d: d["status"] == "in_force"),
    ("hts_revision_diff", {"code": "8517.12.00.50", "rev_a": "2018"}, lambda d: d["change"] == "removed"),
]


def env(extra: dict | None = None) -> dict:
    e = dict(os.environ)
    e.update({"DATA_DIR": str(FIXTURE_DATA), "USE_VECTORS": "false"})
    e.update(extra or {})
    return e


async def exercise(client: Client, redact: bool = False) -> None:
    tools = await client.list_tools()
    assert {t.name for t in tools.tools} == EXPECTED
    for name, args, check in CALLS:
        res = await client.call_tool(name, args)
        assert not res.is_error, (name, res.content)
        data = res.structured_content
        assert data is not None and check(data), (name, data)
    gri = await client.read_resource("hts://gri")
    assert "INTERPRETATION" in gri.contents[0].text.upper()
    notes = await client.read_resource("hts://notes/chapter/42")
    assert "leather" in notes.contents[0].text.lower()
    if redact:
        g = INFO["goldens"][0]
        res = await client.call_tool("get_ruling", {"id": g})
        assert res.structured_content["found"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("redact", [False, True])
async def test_stdio_transport(redact):
    args = ["-m", "tariffagent.mcp_server.server", "--transport", "stdio", "--no-vectors"] + (["--redact-eval"] if redact else [])
    params = StdioServerParameters(command=sys.executable, args=args, env=env())
    async with Client(params) as client:
        await exercise(client, redact)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def http_server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "tariffagent.mcp_server.server", "--transport", "http", "--host", "127.0.0.1",
         "--port", str(port), "--no-vectors", "--redact-eval"],
        env=env(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/mcp"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.anyio
async def test_streamable_http_transport(http_server):
    async with Client(http_server) as client:
        await exercise(client, redact=True)


@pytest.fixture
def anyio_backend():
    return "asyncio"
