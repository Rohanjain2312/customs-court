# Phase checklist

Derived from `TARIFFAGENT_FINAL_PLAN.md`, which stays the source of truth. Each phase ends with a commit, a push, and a note in `docs/PROGRESS.md`.

## Phase 0: Data foundation
- [ ] HTS current release tree with revision id on every row (USITC exportList)
- [ ] Section notes, chapter notes, GRI text
- [ ] Past revisions (basic editions 2018 to 2026) for the time machine and diff tool
- [ ] ATLAS splits loaded (official test split intact)
- [ ] CROSS metadata for all rulings (status cross references), full texts for the corpus and the fresh set
- [ ] Mirror text spot-checked against CROSS
- [ ] Crosswalk and `code_stale`
- [ ] SQLite FTS5 plus local embedding index, fused with RRF
- [ ] `ruling_status` derivation plus a 50-ruling hand-labeled check set, accuracy reported
- [ ] `tariffagent data status` prints counts, date ranges, stale rate, status distribution
- [ ] Parsing and status tests

## Phase 1: MCP server
- [ ] FastMCP, one tool implementation, stdio and stateless Streamable HTTP at 0.0.0.0:8000/mcp
- [ ] 8 tools with pydantic output, 2 resources
- [ ] `--redact-eval` with a test that proves goldens cannot be fetched or found
- [ ] Untrusted-data wrapping and a poisoned-ruling test (recorded fixture)
- [ ] Integration tests over stdio and HTTP; Claude Code config tested

## Phase 2: Agent Skill
- [ ] Study anthropics/skills and agentskills.io, note borrowings in ARCHITECTURE.md
- [ ] `skills/gri-classification/SKILL.md` under 5,000 tokens
- [ ] 8 to 10 worked examples from real rulings in `references/`
- [ ] `scripts/validate_hts.py`
- [ ] End-to-end test with skill plus MCP tools (fixture, and one `-m live`)

## Phase 3: Single-agent baseline
- [ ] Provider adapters: Anthropic (live), OpenAI (subset), Bedrock and Vertex (mocked)
- [ ] Prompt caching with logged cache tokens
- [ ] Structured `Classification` output
- [ ] Tool loop with turn and token caps, jsonl traces, response cache
- [ ] Splits fixed before prompt work; tune on dev_100 only

## Phase 4: Eval harness
- [ ] Datasets with manifests: atlas_test_200, fresh_N, dev_100, subset
- [ ] Metrics: digit-level accuracy, citation validity, abstain, calibration, judge, cost, latency
- [ ] Read 50+ failures, taxonomy, distribution
- [ ] Baselines: zero-shot, ATLAS published, single agent
- [ ] Batch API for non-interactive runs, `make eval-smoke` from recordings

## Phase 5: Multi-agent
- [ ] Orchestrator, parallel advocates, single adjudicator, typed events
- [ ] Arms A, B (token matched), C (smart friend), D (multi-agent)
- [ ] A and D on atlas_test_200; B, C and repeats on the subset as budget allows
- [ ] Slices and hypothesis test with CIs

## Phase 6: Deploy-ready packages (nothing deployed)
- [ ] AWS: Dockerfile, AgentCore entrypoint, Terraform, Bedrock adapter (mocked), local validation
- [ ] GCP: Dockerfile, Cloud Run spec, ADK agent, Vertex adapter (mocked), local validation
- [ ] Guarded deploy and destroy scripts with cost estimates; smoke-test script
- [ ] SECURITY.md, ARCHITECTURE.md with diagrams and comparison table
- [ ] Optional free HF Space hosting (only if clearly free)

## Phase 7: Vertical depth
- [ ] GRI 3(b) composites and sets with tests
- [ ] Parts and accessories exclusions as a checked step
- [ ] Revoked-ruling handling
- [ ] Ask-for-missing-facts mode, measured

## Phase 8: Customs Court demo
- [ ] FastAPI SSE backend with typed events
- [ ] Vite, React, TypeScript, D3, Tailwind frontend
- [ ] Replay mode default, 10+ recorded exhibits
- [ ] Playwright tests, screenshots, video and GIF

## Phase 9: Polish
- [ ] README, CASE_STUDY, WALKTHROUGH, blog draft, resume bullet
- [ ] CI with no live calls
- [ ] Secrets scan, number audit, final make test, eval-smoke, cost
