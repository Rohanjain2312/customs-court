# Claude Code MCP check (2026-09-28)

Claude Code 2.1.284 (bundled with the desktop app).

- `claude mcp add --scope local tariffagent-local -- uv run --directory <repo> tariffagent-mcp --transport stdio` then `claude mcp get tariffagent-local`: Status: Connected, Type: stdio.
- HTTP server started with `tariffagent-mcp --transport http --host 127.0.0.1 --port 8765`, then `claude mcp add --scope local --transport http tariffagent-http http://127.0.0.1:8765/mcp` and `claude mcp get tariffagent-http`: Status: Connected, Type: http.
- The project-scoped `.mcp.json` entry shows "Pending approval" until a user approves it in an interactive `claude` session. That is expected Claude Code behavior.
- Tool listing over both transports is covered by `tests/test_mcp_transports.py` with the official MCP SDK client (8 tools, 2 resources). Listing tools from inside Claude Code needs a model session, which was not run to avoid spend.
