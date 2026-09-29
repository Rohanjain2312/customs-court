# Customs Court

TariffAgent classifies product descriptions into 10-digit US HTS codes, grounds every answer in CBP CROSS rulings, and checks whether the rulings it relies on are still in force. It ships as an MCP server and an Agent Skill.

(Full product page, results and demo come in Phase 9. See `docs/PROGRESS.md` for current state.)

## MCP quickstart

Install:

```bash
git clone https://github.com/Rohanjain2312/customs-court && cd customs-court
uv sync --extra embed
make data   # builds data/tariffagent.sqlite (cached, resumable)
```

The server exposes 8 read-only tools (`hts_navigate`, `hts_search`, `get_notes`, `get_gri`, `cross_search`, `get_ruling`, `ruling_status`, `hts_revision_diff`) and 2 resources (`hts://gri`, `hts://notes/chapter/{chapter}`). All corpus text comes back inside `untrusted_corpus_text` objects.

### stdio

```bash
uv run tariffagent-mcp --transport stdio
```

### Streamable HTTP (stateless, JSON responses)

```bash
uv run tariffagent-mcp --transport http --host 127.0.0.1 --port 8000   # endpoint: http://127.0.0.1:8000/mcp
```

Add `--redact-eval` to hide every ruling that belongs to an evaluation set. Add `--no-vectors` to skip the local embedding model (keyword search only).

### Claude Code

```bash
claude mcp add tariffagent -- uv run --directory /path/to/customs-court tariffagent-mcp --transport stdio
# or, against a running HTTP server:
claude mcp add --transport http tariffagent-http http://127.0.0.1:8000/mcp
```

The repo also has a project-scoped `.mcp.json`; Claude Code asks you to approve it the first time.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tariffagent": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/customs-court", "tariffagent-mcp", "--transport", "stdio"]
    }
  }
}
```

## License

MIT
