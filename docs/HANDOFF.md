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

- Rohan's budget for this project is spent. Paid API spend stopped at $13.34 (`make cost`; Anthropic $12.70, OpenAI $0.64). `BUDGET_USD_TOTAL` in `.env` is set to $13.19, below what is already spent, so any paid call now fails closed. The Anthropic account limit was also hit and will not be raised.
- Free routes tried, in order: GitHub Models (endpoint only answers "OK"), a local open-weights model with llama.cpp (worked, overheated the MacBook, stopped), Hugging Face Jobs on the PRO plan's included credit (built and dry-run tested end to end; the launch was refused because the month's credit was already used, and nothing was charged), Mistral's free API tier (the console offers only paid plans now; the key in `.env` has a 0 requests/minute limit and is unused).
- What finished it: the test-set and fresh-set agent runs were done blind by Claude Opus 5.5 inside the Claude Code session (covered by Rohan's plan, no API spend) on `subset_80` and `fresh_40`, through `scripts/agent_tools.py` (a client of the MCP server with `--redact-eval`) and scored by `scripts/score_blind.py`. The no-tools controls (Claude Sonnet 5.5) and the two reasoning judges (Claude Opus 5.5, Claude Haiku 4.5) ran the same way. Protocol in `evals/reports/cc-subset80-A.json`.
- The Claude Code session itself hit its usage limit once (2026-09-30). Rohan asked that background helpers use Sonnet 5.5 from then on, so the controls were rerun on Sonnet 5.5 instead of mixing models.
- The HF Job path is still ready if Rohan ever wants the open-weights runs: `bash scripts/hf_job/auto_run.sh "<UTC time after the credit refills>"`. It cannot bill beyond included credits.
- Cleaned up 2026-09-30: the Mistral key is removed from `.env`, and the private HF dataset `rohanjain2312/customs-court-evaljobs` is deleted (`scripts/hf_job/push_bundle.py` recreates it if the HF Job path is ever used).

### 1. Build status (final, 2026-09-30)

Done and pushed: every phase in the plan, with these limits.

Finished runs (reports in `evals/reports/`, tables rebuilt by `scripts/results_tables.py`):
- Zero-shot baselines on the API: `atlas200-Z`, `fresh150-Z` (Claude Sonnet 5), `subset80-O` agent on gpt-5-mini.
- Dev runs on the API: `dev100-A`, `dev40-A-v1`, `dev10-D`, `dev10-D-v2`, `pilot-dev20-A` (Sonnet 5.5).
- Blind in-session runs (date-limited reruns `cc-subset80-A-asof`, `cc-fresh40-A-asof` on Sonnet 5.5 also done): `cc-subset80-A`, `cc-fresh40-A` (agent), `cc-subset80-Z`, `cc-fresh40-Z` (no-tools controls), with judge reports `cc-subset80-A.judge.json`, `cc-fresh40-A.judge.json`.

Done in the session at $0 (2026-10-01): ask-for-facts mode on all 80 subset items, a 20-item multi-agent pilot, and a real Objection exhibit (see `docs/EVAL.md`).

Not run, and not going to be (paid API budget is gone; never use paid APIs again): the Claude Sonnet 5 API agent on the test split, and the controlled multi-agent study (arms B, C, D on `subset_80`). `scripts/eval_full.sh` runs them if a budget ever exists; every response is cached.

Known gaps:
- The date limit reaches 76 of 80 subset items and all 40 fresh items. For 39 of the subset items the date is the earliest of several candidate source rulings (conservative).
- The Opus 5.5 rows predate the second source-ruling linker; that run cited a candidate source ruling 12 times, so its numbers may be inflated. The Sonnet 5.5 rows are the clean comparison. Rerunning Opus would need usage headroom.
- ATLAS labels are noisy: 5 subset packets have a gold code that disagrees with the CBP text beside it (judge 1 flagged them).
- `evals/reports/localtest-2b.json` is from the short local-model trial that overheated the laptop. Not used in any table. Its raw traces (`evals/runs/localtest-2b/`) are git-ignored.

### Other handoff items
- `evals/audit/audit_25.md` (25 judge cases) was reviewed by Claude on 2026-09-30: 21 pass, 4 fail. A human check is optional; nothing depends on it.
- The GitHub repo is public (done by Rohan). Secrets scan done 2026-09-30 over the full git history: no Anthropic, OpenAI, Hugging Face or GitHub token appears; the only key-shaped string is the fake placeholder `AKIASCRIPTEDLOCAL000` in a deploy test. `.env` was never committed. Command: `gh repo edit Rohanjain2312/customs-court --visibility public --accept-visibility-change-consequences`
- Cloud deploys: never run by this build. `make deploy-aws` / `make deploy-gcp` refuse unless `I_ACCEPT_CLOUD_COSTS=yes`.
