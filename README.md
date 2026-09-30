# Customs Court

TariffAgent classifies a product description into a 10-digit US HTS code the way a customs broker would. It applies the General Rules of Interpretation, reads section and chapter notes, grounds the answer in CBP CROSS rulings, and checks whether each ruling it relies on is still in force. It ships as an MCP server, a reusable Agent Skill, a multi-agent "court", deploy-ready AWS and Google Cloud packages, and a courtroom demo.

![Customs Court demo: the Objection flow](docs/demo.gif)

## What is in the box

| Piece | What it does | Where |
|---|---|---|
| MCP server `tariffagent` | 8 read-only tools over the HTS tree, notes, GRI and 44,139 CROSS rulings with derived status. stdio and stateless Streamable HTTP, one implementation. `--redact-eval` hides evaluation rulings. | `src/tariffagent/mcp_server/` |
| Agent Skill `gri-classification` | The broker workflow in under 2,500 tokens, 9 worked examples from real rulings, and a code validator script. Names the MCP tools it uses. | `skills/gri-classification/` |
| Single agent | Claude (or any provider behind the adapter) with tool use, prompt caching, structured output, a checked final step and one repair turn. | `src/tariffagent/agents/single.py`, `checks.py` |
| Multi-agent court | Orchestrator, parallel heading advocates (read only), one adjudicator that writes the answer. Typed events for the demo. | `src/tariffagent/agents/multi.py` |
| Eval harness | Fixed datasets with sha256 manifests, digit-level accuracy with bootstrap CIs, citation validity, calibration, reference-grounded judge with a second judge, failure taxonomy, cost ledger, response cache. | `src/tariffagent/evals/`, `evals/` |
| Deploy-ready packages | AWS (AgentCore, Bedrock, Terraform) and Google Cloud (Cloud Run, ADK, Vertex). Built and validated locally. **Deploy-ready, not deployed, to keep cost at zero.** | `deploy/` |
| Customs Court demo | Replay-first courtroom UI: live HTS tree, advocate cards, ruling panel, Objection button, Beat the Broker, time machine, cost meter. | `demo/` |

## Results

Test set: the published ATLAS test split (200 CBP rulings). Percentages are exact-match rates with 95% bootstrap intervals. Codes that no longer exist in today's HTS are scored at 6 digits and excluded from the 10-digit column. Abstentions count as misses unless the agent still gave a code.

<!-- results:headline -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| ATLAS fine-tuned LLaMA-3.3-70B (published) | paper | 40.0% | 57.5% | | | |
| GPT-5-Thinking (published in ATLAS) | paper | 25.0% | | | | |
| Gemini-2.5-Pro-Thinking (published in ATLAS) | paper | 13.5% | | | | |
| Zero-shot, no tools | Claude Sonnet 5 | 21.3% [14.9, 27.6] | 53.0% [46.0, 60.0] | 62.0% [55.5, 68.5] | 13.5% | $0.0061 |
| Zero-shot, no tools | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| TariffAgent single agent (A) | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| TariffAgent multi-agent (D) | Qwen3.5-4B (open weights) advocates, Qwen3.6-35B-A3B (open weights) adjudicator | not run yet | | | | |
<!-- /results:headline -->

Post-training-cutoff set: 150 CBP rulings dated 2026-07-01 or later, after every model's training cutoff, reported separately.

<!-- results:fresh -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Zero-shot, no tools | Claude Sonnet 5 | 20.0% [14.0, 26.7] | 48.0% [40.0, 56.0] | 69.3% [61.3, 76.7] | 1.3% | $0.0060 |
| Zero-shot, no tools | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| TariffAgent single agent (A) | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
<!-- /results:fresh -->

How the budget shaped these numbers, plainly:
- The Claude agent was built, tuned and error-analyzed with Claude Sonnet 5 on the dev split. The project's API budget ran out before the Claude agent could run on the test split. The Claude zero-shot baseline did run on both test sets.
- The agent runs on the test sets use open-weights models (Qwen3.6-35B-A3B and Qwen3.5-4B) served by vLLM on a Hugging Face Job paid from included plan credits, so they cost nothing extra. Same tools, skill, prompts, checks and datasets.
- The Claude agent's dev numbers are in `docs/EVAL.md`. They are for prompt work, not a test result.

Cost:

<!-- results:cost -->
| | USD |
|---|---|
| Paid API spend, whole project | $13.18 |
| Same calls at list price, no caching, no batch discount | $39.30 |
| Saving from prompt caching and the Batch API | 66.5% |
| Share of input tokens read from the prompt cache | 81.3% |
| Open-weights runs (HF Job, included PRO credits) | $0 extra |
<!-- /results:cost -->

Every number above comes from a file in `evals/reports/` (`scripts/number_audit.py` checks this). Full write-up: `docs/CASE_STUDY.md`.

## MCP quickstart

```bash
git clone https://github.com/Rohanjain2312/customs-court && cd customs-court
uv sync --extra embed
make data   # builds data/tariffagent.sqlite from USITC and CBP CROSS (cached, resumable, polite)
```

Tools: `hts_navigate`, `hts_search`, `get_notes`, `get_gri`, `cross_search`, `get_ruling`, `ruling_status`, `hts_revision_diff`. Resources: `hts://gri`, `hts://notes/chapter/{chapter}`. All corpus text comes back inside `untrusted_corpus_text` objects, and documents that try to instruct an AI model are flagged.

stdio:

```bash
uv run tariffagent-mcp --transport stdio
```

Streamable HTTP (stateless, endpoint `http://127.0.0.1:8000/mcp`):

```bash
uv run tariffagent-mcp --transport http --host 127.0.0.1 --port 8000
```

Claude Code:

```bash
claude mcp add tariffagent -- uv run --directory /path/to/customs-court tariffagent-mcp --transport stdio
```

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

## Install the skill

Copy `skills/gri-classification/` into your skills folder (for Claude Code, `~/.claude/skills/` or the project's `.claude/skills/`). The skill calls the MCP tools above; `scripts/validate_hts.py` checks a final code with the standard library only.

## Run the demo

```bash
uv sync --extra demo
make replay     # no API key, no network, no spend: recorded hearings with compressed timing
```

Live mode (`make demo`) needs `ANTHROPIC_API_KEY` and stops each browser session at $2.

## Reproduce the evals

Every model response is stored in an on-disk cache keyed by the full request, so re-running a finished eval costs nothing.

```bash
make test         # offline, recorded responses
make eval-smoke   # re-scores committed runs and replays a recorded classification
uv run tariffagent eval run --dataset atlas_test_200 --arm A --mode batch   # Claude, spends money
uv run python scripts/hf_job/launch.py run --tag mine --plan A --flavor rtx-pro-6000 --timeout 43m   # open weights on HF Jobs
uv run python scripts/results_tables.py   # rebuild every table in the docs from evals/reports
```

## Deploy-ready, not deployed

`make build-deploy-aws` and `make build-deploy-gcp` build the images and validate them locally (MCP calls against the running containers, `terraform validate`, the ADK agent against the local MCP server). `make deploy-aws` and `make deploy-gcp` print a cost estimate from the current pricing pages and refuse to run unless `I_ACCEPT_CLOUD_COSTS=yes`. Nothing was deployed, so nothing was billed. See `docs/ARCHITECTURE.md` and `docs/SECURITY.md`.

## Docs

`docs/CASE_STUDY.md` (results and what they mean), `docs/EVAL.md` (data, datasets, metrics, error analysis), `docs/ARCHITECTURE.md` (components, diagrams, cloud designs), `docs/SECURITY.md`, `docs/WALKTHROUGH.md` (5 and 12 minute talk tracks).

## License

MIT
