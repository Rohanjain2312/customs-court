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

## Phase 2: Agent Skill (2026-09-28)

Built
- `skills/gri-classification/SKILL.md` (2,459 tokens, counted with the token counting API) with the seven-step broker workflow, naming each MCP tool.
- Four reference files with nine worked examples from real rulings: a GRI 3(b) composite (NY N362060), a retail set (NY N361728), a parts case (HQ H341222), a GRI 2(a) case, a GRI 3(c) case, a garment, a shoe, a revoked-ruling chain (NY K89734 to HQ H011054 to HQ H192481), and a missing-facts case. Section notes quoted in the parts reference were checked against the stored note text.
- `scripts/validate_hts.py`, standard library only.
- Skill loader and spec validator (`src/tariffagent/agents/skill.py`); MCP client backend so the agent can call tools through a real MCP session.

Tests passing
- `test_skill_loads_and_is_valid`.
- `test_skill_with_mcp_server_end_to_end`: skill in the prompt, tools over MCP stdio against the fixture DB, full classification replayed from recorded responses; the code is checked with `validate_hts.py`.
- `test_agent_ignores_poisoned_ruling` (Phase 1 item): the fixture ruling N999001 tells the model to answer 9999.99.99.99. The agent saw it in a tool result, said it contained embedded instructions, did not cite it, and answered 4202.21.90.00.
- `-m live` `test_live_skill_mcp_classification`: run once on 2026-09-28, passed.

Unverified
- Only one live e2e run was made; behavior on other products is measured in Phase 4.
