# Handoff

Things Rohan may need to do, plus the state of the environment. Updated as work goes on.

## Environment check (2026-09-28)

| Item | State |
|---|---|
| `ANTHROPIC_API_KEY` | Present in `.env` (copied from `loan-servicing-agent/.env` with Rohan's approval) |
| `OPENAI_API_KEY` | Present in `.env` (same source, same approval) |
| `HF_TOKEN` | Present at `~/.cache/huggingface/token` (account rohanjain2312). Not copied into `.env`. |
| `gh auth status` | Logged in as Rohanjain2312, scopes repo and workflow |
| GitHub repo | https://github.com/Rohanjain2312/customs-court, private, remote `origin`, branch `main` |
| uv | 0.x at `~/.local/bin/uv`, Python 3.12 |
| Node | v24.21.0 LTS, installed to `~/.local/opt` from nodejs.org (checksum verified) |
| Terraform | 1.16.4, installed to `~/.local/bin` from releases.hashicorp.com (checksum verified) |
| Docker | Docker CLI 29.8.1 plus Colima 0.10.3 and Lima 2.2.0 (user-local, no admin). Colima VM: 4 CPU, 6 GB RAM, 40 GB disk, vz, arm64 |
| Homebrew | Not installed. Not needed. |

To use the tools in a new shell: `export PATH=~/.local/bin:~/.local/opt/lima/bin:$PATH`, then `colima start` if Docker is needed.

## Open items for Rohan

### 1. BLOCKER: Anthropic account usage limit (2026-09-29 00:53 UTC)

Every Claude call now returns: `400 invalid_request_error: You have reached your specified API usage limits. You will regain access on 2026-10-01 at 00:00 UTC.`

This is a spend limit set on the Anthropic account (Console > Settings > Limits), not this project's budget. This project had spent $2.91 of its $40 cap when it hit. Other projects on the same key count toward the account limit.

Why it matters: the evaluation runs (baseline on dev_100, arms A and D on atlas_test_200, the fresh set, arms B and C) all need Claude.

What to do (either one):
- Raise the monthly limit at https://platform.claude.com/settings/limits, or
- Wait until 2026-10-01 00:00 UTC, then resume with the commands in "Resume the eval runs" below.

Everything is cached, so resuming re-uses every response already paid for.

### 2. Where the build stopped (2026-09-29)

Done and pushed: Phase 0 (data), Phase 1 (MCP server, stdio + HTTP, Claude Code check), Phase 2 (Agent Skill), Phase 3 (single-agent baseline code, adapters, batch runner, datasets: atlas_test_200, dev_100, fresh_300, subset_80). Eval harness, judge, taxonomy and multi-agent code are written and unit-tested with fakes.

Not done yet:
- Phase 4 results: dev_100 baseline (4 batch rounds were paid for and cached; rerun resumes), error analysis of 50+ failures, zero-shot baseline, headline runs. Needs the Anthropic limit fix above.
- Phase 5 study runs (arms A, B, C, D). Code exists in `src/tariffagent/agents/`.
- Phase 6 deploy packages and Phase 8 frontend: two background builders were started and then stopped when the session hit its own usage limit. Partial, unreviewed, uncommitted files may exist in `deploy/` and `demo/frontend/`. Review before use.
- Phases 7 and 9 (vertical depth, README product page, case study, walkthrough).
- The corpus was frozen after the text fetch finished (44,139 rulings with text); a background job re-embeds new rulings (`data/logs/embed2.log`).

### Resume the eval runs

```bash
uv run tariffagent eval run --dataset dev_100 --arm A --mode batch --run-id dev100-A --phase baseline
uv run tariffagent eval run --dataset atlas_test_200 --arm Z --mode batch --phase baseline
uv run tariffagent eval run --dataset atlas_test_200 --arm A --mode batch --phase headline
uv run tariffagent eval run --dataset atlas_test_200 --arm D --mode batch --phase headline
```

### Other handoff items
- Making the GitHub repo public: only after a secrets scan. `gh repo edit Rohanjain2312/customs-court --visibility public --accept-visibility-change-consequences`
- Cloud deploys: never run by this build. `make deploy-aws` / `make deploy-gcp` refuse unless `I_ACCEPT_CLOUD_COSTS=yes`.
