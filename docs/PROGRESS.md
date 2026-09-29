# Progress

## Phase 0: Data foundation (2026-09-28)

Built
- HTS ingestion (`src/tariffagent/data/hts.py`): current release 2026HTSRev20 with revision id on every row, chapter and section notes, GRI text, and nine past basic editions (2018 to 2026).
- CROSS ingestion (`src/tariffagent/data/cross.py`): metadata for 218,847 rulings (98.6% of what CROSS reports), verified mirror texts (40,223), and direct CROSS texts for everything since 2025-07-01.
- ATLAS loader and ruling linker (`src/tariffagent/data/atlas.py`), with redaction rows for the test and validation splits.
- Crosswalk and `code_stale` (`src/tariffagent/data/crosswalk.py`).
- Ruling status derivation (`src/tariffagent/data/status.py`) with a hand-labeled 50-case check set and two held-out sets. Accuracy in `docs/EVAL.md`.
- Hybrid index (`src/tariffagent/index/search.py`): SQLite FTS5 plus local `BAAI/bge-small-en-v1.5` vectors, fused with reciprocal rank fusion.
- Budget-enforced spend ledger, on-disk response cache, config module.

How to run
- `make data` runs the whole pipeline (resumable, raw responses cached under `data/raw/`).
- `uv run tariffagent data status` prints counts, date ranges, stale-code rate and status distribution.

Tests passing
- `tests/test_data_parsing.py` (tree building, code helpers, notes HTML, ATLAS parsing, status text rules).

Unverified or open
- The CROSS full-text fetch for 2025-07 onward was still running at commit time (about 1,300 of 3,916 done). Re-run `make data` to finish; it resumes.
- The embedding index was still building at commit time.
- Mirror texts dropped for failing verification (14,298) are not replaced. Older rulings outside the verified set have metadata only.
- 1.4% of CROSS rulings are missing from the metadata harvest.

## Phase 1: MCP server (2026-09-28)

Built
- `src/tariffagent/mcp_server/`: one tool implementation (`tools/core.py`) wrapped by `MCPServer` from the official Python MCP SDK 2.2 (FastMCP was renamed `MCPServer` in SDK 2.x). Entry point `tariffagent-mcp` with `--transport stdio|http`. HTTP is stateless Streamable HTTP with JSON responses at `/mcp`; no legacy SSE.
- 8 tools returning pydantic models, 2 resources (`hts://gri`, `hts://notes/chapter/{chapter}`).
- `--redact-eval` hides every ruling in `eval_redactions` from get, search, status and linked-ruling lists. It answers "not found" rather than "redacted" so it does not leak which rulings are goldens.
- Corpus text is wrapped in `untrusted_corpus_text` objects with a fixed notice.
- DNS rebinding protection is on by default for loopback hosts; container deployments set `MCP_ALLOWED_HOSTS`.
- A 12 MB fixture database built from real data (`scripts/build_fixture_db.py`) with one synthetic poisoned ruling.

How to run
- `make mcp-stdio`, `make mcp-http`. Claude Code and Claude Desktop snippets are in the README.

Tests passing
- `tests/test_mcp_tools.py` (11 tests incl. redaction of goldens from get, search by subject, search by id, and status; untrusted wrapping of the poisoned ruling).
- `tests/test_mcp_transports.py`: every tool and both resources over stdio (with and without `--redact-eval`) and over Streamable HTTP, using the SDK `Client`.
- Claude Code 2.1.284: `claude mcp get` shows Connected for both a stdio and an HTTP registration (`evals/reports/mcp_claude_code_check.md`).

Unverified or open
- The agent-level poisoned-ruling test needs the agent, so it lands in Phase 3.
- Listing tools from inside a Claude Code model session was not run (it would spend tokens); tool listing is covered by the SDK client tests.
