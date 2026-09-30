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

## Phase 3: Single-agent baseline (2026-09-29)

Built
- Provider adapters behind one interface (`src/tariffagent/llm/`): Anthropic (live), OpenAI Chat Completions (subset only), Bedrock (AnthropicBedrockMantle) and Vertex (Claude and Gemini) as mocked code paths that refuse to build a real client without `I_ACCEPT_CLOUD_COSTS=yes`.
- Prompt caching: two breakpoints, one at the end of the static prefix (tools, role, skill body, GRI text) and one at the end of the conversation so each turn reads the previous one. Cache read and write tokens go to the ledger. Batch runs use the 1-hour TTL because rounds can be minutes apart.
- Structured output `Classification` through `output_config.format` (hts10, facts, gri_path, deciding_gri, cited_rulings with status, rejected_alternatives, missing_facts, confidence, abstain, rationale).
- Tool loop with hard caps on turns and tokens, a forced final answer when the cap is hit, typed events, and a jsonl trace per run.
- One episode generator driven two ways: interactive threads, or lockstep rounds through the Message Batches API (50% off; the pricing page says the discount stacks with cache multipliers). Every request goes through the on-disk response cache, so re-runs are free.
- Splits fixed before prompt work: `atlas_test_200`, `dev_100` (seeded sample of ATLAS validation), `fresh_300`, `subset_80` (see `evals/datasets/manifest.json`).
- Model settings verified 2026-09-28: Sonnet 5.5 rejects non-default temperature (so it is left unset), forced tool choice returns 400 (not used), SDK 1.x dropped `temperature` from the method signature (Haiku gets temperature 0 through `extra_body`).

Tests passing
- `tests/test_providers_mocked.py` (7): cache breakpoints, structured output params, Haiku temperature path, Bedrock and Vertex Claude through mocked httpx2 transports, Gemini request translation and usage mapping, cloud opt-in guard, OpenAI translation and cached-token accounting.
- `tests/test_multi_agent_flow.py` (2): scripted fake model through the interactive and batched runners.

Pilot (dev, 20 items, interactive): 10-digit 7/16, 6-digit 12/20, $0.036 per item, cache hit rate 70%, p50 11 s. Spend so far $0.88.

## Model switch (2026-09-29)

At Rohan's request the reasoner moved from Claude Sonnet 5.5 to Claude Sonnet 5. No Sonnet model is cheaper per token than Sonnet 5.5 (pricing page, checked 2026-09-29: Sonnet 5 and 5.5 are both $2/$10 per million tokens, Sonnet 4.6 and 4.5 are $3/$15), so Sonnet 5 is the cheapest option that is not Sonnet 5.5. Savings came from caching instead:
- Batch cache pre-warm (`AnthropicProvider.prewarm`): requests inside one Message Batch run concurrently, so each paid its own 1-hour cache write of the 7.4k-token static prefix. One interactive call now writes it once. On round 1 of dev_100, cost per request fell from $0.0109 to $0.0021 (`evals/reports/caching_prewarm.json`). `max_tokens=0` would be the natural pre-warm, but the API refuses it with structured output, and the output schema is part of the cached prefix (dropping it changed the prefix by about 1,100 tokens), so the pre-warm asks for one token.
- The pilot (pilot-dev20-A) is the only run on Sonnet 5.5 and is labeled so.

## Phase 4: Eval harness (2026-09-29)

Built
- Datasets: `atlas_test_200`, `dev_100`, `fresh_300` and a seeded `fresh_150` sample, `subset_80` (manifest with sha256 in `evals/datasets/manifest.json`).
- Metrics, bootstrap CIs, reference-grounded judge with a second judge from another vendor, `eval judge`, `eval compare`, `eval taxonomy` commands.
- Error analysis: all 59 failures of `dev100-A` read and tagged (`evals/taxonomy/dev100-A.jsonl`, distribution in `evals/reports/dev100-A.taxonomy.json`). The biggest group, 18 of 59, has a questionable gold: 14 of those are descriptions that list several different articles while the gold is one of them. 21 of 59 were abstentions. Four causes were added after reading.
- Prompt v1.2 (dev only): best-guess code even when abstaining, first-named article for multi-article descriptions, navigate the 8-digit line before choosing the statistical suffix. On the same 40 dev items v1.2 matched v0 within noise (dev40-A-v1).

Runs finished: `atlas200-Z`, `fresh150-Z` (zero-shot baselines), `dev100-A`, `dev40-A-v1`, `subset80-O` (OpenAI comparison). The API budget closed before the Claude agent ran on test; see Phase 9.

## Phase 5: Multi-agent (2026-09-29, test-set study not run)

- Live check on 10 dev items (dev10-D): works end to end, $0.153 per item interactive. Advocates were 61% of that because each had its own system prefix. After moving the heading to the user turn (shared cache), three advocates of four turns, and no `get_ruling` for advocates: $0.101 per item interactive (dev10-D-v2).
- Batched runs found a real bug the fake-model tests could not: parallel advocate ids contained `#`, which the Batch API rejects. Ids are now mapped to the allowed pattern (test added).

## Phase 6: Deploy-ready packages (2026-09-29)

Built and validated locally, nothing deployed. See `docs/ARCHITECTURE.md` (deployment sections, comparison table) and `docs/SECURITY.md`.
- `make build-deploy-aws`: arm64 MCP and agent images, all 8 tools called over MCP against the container, redaction verified, agent `/invocations` with a scripted Bedrock model, `terraform validate` passes.
- `make build-deploy-gcp`: amd64 image, Cloud Run spec with no public invoker, ADK agent run locally against the local MCP server with scripted models.
- Deploy and destroy scripts print a cost estimate and refuse without `I_ACCEPT_CLOUD_COSTS=yes` (tested).
- Unverified: anything that needs a cloud account (IAM, JWT and ID-token auth, cold starts, real cost).

## Phase 7: Vertical depth (2026-09-29)

- `agents/checks.py`: a checked final step on every answer, through the same tool backend. The code must be a current 10-digit line (lists the real lines when not), a parts provision must name the parts rule applied, cited rulings must exist, must not be flagged, and must not be revoked without saying so. One repair turn when a check fails (7 repairs in 37 finished dev40-A-v1 items).
- `ruling_status` returns `replaced_by` for revoked and modified rulings (id, date, codes).
- Documents that address an AI model are flagged (`injection_warning`, `contains_instructions_to_ai`). 0 of 44,139 real rulings trip it. Sonnet 5 had cited the planted test ruling as in force; the checker now blocks that and the poison test asserts it.
- Ask-for-facts mode (`--ask-mode`). Built and tested; not measured on the subset (budget).
- Tests: `tests/test_checks.py` (9).

## Phase 8: Customs Court demo (2026-09-29)

- FastAPI backend with SSE replay (compressed timing) and a gated live mode ($2 per session cap), React, TypeScript, D3 and Tailwind frontend with all seven features.
- 26 exhibits from real Sonnet 5 recordings, including 10 items with both a single-agent and a multi-agent hearing. The Objection exhibit is a labeled scripted placeholder until one live run is possible.
- Tests: `tests/test_demo_backend.py` (16), Playwright UI (6 passed), video `docs/demo.webm` and `docs/demo.gif` (recorded before the exhibits were switched to Sonnet 5 runs; re-record at the end).

## Phase 9: Evaluation at $0 and docs (2026-09-30)

- Blind in-session runs (Claude in the Claude Code session, no API spend): the agent on `subset_80` and `fresh_40` through the MCP server with `--redact-eval`, scored by `scripts/score_blind.py`; no-tools controls on the same items; two reasoning judges collected by `scripts/judge_blind.py`.
- A first Haiku judge pass that compared strings instead of reading was discarded and rerun one packet at a time. A usage limit stopped an Opus control part way; it was discarded and rerun on Sonnet 5.5.
- The scorer now lists citations dated after the item's own ruling and reports accuracy without them.
- `evals/reports/data_report.json` (`tariffagent data status --write`) is the source for the data figures in `docs/EVAL.md`; the corpus stale-code rate is 28.8% on the frozen corpus.
- Docs: every results table is generated from `evals/reports/`; `scripts/number_audit.py` passes on README, CASE_STUDY, BLOG, EVAL, WALKTHROUGH and RESUME. `evals/audit/audit_25.md` for an optional human check.

## Phase 10: date filter and cleanup (2026-09-30)

- Precedent date filter: `TariffTools` hides rulings dated after a per-request as-of date (context variable; `_meta` key `tariffagent/as_of` over MCP; `ToolExecutor(as_of=...)` in the harness; `TA_ITEM`/`TA_AS_OF` in `scripts/agent_tools.py`). Covers `cross_search`, `get_ruling`, `ruling_status`, `replaced_by` and the hts_search ruling hints. Per-item dates in `evals/datasets/as_of.json` (`scripts/build_as_of.py`): exact for fresh items, from the linked source ruling (score >= 0.6) for 38 of 80 subset items. Tests in `tests/test_mcp_tools.py` and `tests/test_mcp_transports.py` (stdio and HTTP).
- Reruns with the filter on, Claude Sonnet 5.5 in the session: `cc-subset80-A-asof` 45.5% at 10 digits, `cc-fresh40-A-asof` 85.0%. Zero later-dated citations (was 22 on 20 items, and 1). Impact in `evals/reports/as_of_impact.json`.
- Cleanup: Mistral key removed from `.env`; private HF bundle dataset deleted; `evals/runs/localtest-2b/` git-ignored; `evals/audit/audit_25.md` reviewed (21 pass, 4 fail).
