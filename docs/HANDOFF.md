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

### 0. Money: API budget closed; how the evaluation finished at $0 (updated 2026-09-30)

- Rohan's budget for this project is spent. Paid API spend stopped at $13.18 (`make cost`). `BUDGET_USD_TOTAL` in `.env` is locked at $13.19, so any paid call now fails closed. The Anthropic account limit was also hit and will not be raised.
- Free routes tried, in order: GitHub Models (endpoint only answers "OK"), a local open-weights model with llama.cpp (worked, overheated the MacBook, stopped), Hugging Face Jobs on the PRO plan's included credit (built and dry-run tested end to end; the launch was refused because the month's credit was already used, and nothing was charged), Mistral's free API tier (the console offers only paid plans now; the key in `.env` has a 0 requests/minute limit and is unused).
- What finished it: the test-set agent run was done blind by Claude Opus 5.5 inside the Claude Code session (covered by Rohan's plan, no API spend) on `subset_80`, through `scripts/agent_tools.py` (a client of the MCP server with `--redact-eval`) and scored by `scripts/score_blind.py`. Protocol in `evals/reports/cc-subset80-A.json`.
- The HF Job path is still ready if Rohan ever wants the open-weights runs: `bash scripts/hf_job/auto_run.sh "<UTC time after the credit refills>"`. It cannot bill beyond included credits.
- Optional cleanup: the Mistral key in `.env` can be deleted (it has no active plan); the private HF dataset `rohanjain2312/customs-court-evaljobs` holds only the job bundle and can be deleted too.

### 1. Build status and resume point (updated 2026-09-29 22:45 UTC)

The Anthropic usage limit from 2026-09-29 00:53 UTC was lifted by Rohan. The reasoner moved from Claude Sonnet 5.5 to Claude Sonnet 5 at Rohan's request (same list price; no Sonnet is cheaper per token). Runs before that switch (pilot-dev20-A) used Sonnet 5.5 and are labeled so.

Done and pushed: phases 0 to 3, phase 7 code (checked final step, revoked-ruling replacements, injection flag, ask mode), phase 8 demo (two exhibits are labeled placeholders until real runs exist).

Finished runs (reports in `evals/reports/`):
- `atlas200-Z` zero-shot, `fresh150-Z` zero-shot
- `dev100-A` single-agent baseline with the v0 prompt (before the checked step existed)

Next steps in order (each run resumes from the response cache, so nothing is paid twice):
1. Error analysis of dev100-A failures, taxonomy tags in `evals/taxonomy/dev100-A.jsonl`.
2. Re-record the test fixtures (`TARIFFAGENT_LIVE=1 TARIFFAGENT_RECORD=1 uv run pytest tests/test_agent_e2e.py -k "end_to_end or poisoned"`).
3. Headline runs `atlas200-A`, `atlas200-D`, then `fresh150-A`, then the subset arms (see `scripts/eval_full.sh`).
4. Phase 6 deploy packages: a builder stopped mid-way (session limit). Its files in `deploy/`, `docs/SECURITY.md`, `docs/diagrams/`, `docs/ARCHITECTURE.md` are unreviewed and uncommitted.
5. Real multi-agent and Objection exhibits for the demo, then the video again.
6. Phase 9 docs.

### Other handoff items
- Making the GitHub repo public (your decision). Secrets scan done 2026-09-30 over the full git history: no Anthropic, OpenAI, Hugging Face or GitHub token appears; the only key-shaped string is the fake placeholder `AKIASCRIPTEDLOCAL000` in a deploy test. `.env` was never committed. Command: `gh repo edit Rohanjain2312/customs-court --visibility public --accept-visibility-change-consequences`
- Cloud deploys: never run by this build. `make deploy-aws` / `make deploy-gcp` refuse unless `I_ACCEPT_CLOUD_COSTS=yes`.
