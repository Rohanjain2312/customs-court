# Customs Court replays

Each `*.jsonl` file in this folder is one recorded hearing. The demo backend
(`demo/backend/app.py`) lists them at `GET /api/exhibits` and streams one at
`GET /api/replay/{exhibit_id}` as server-sent events. Replays need no API key and no network.

Do not edit replay files by hand. Edit `exhibits.json` and run:

    uv run python scripts/make_replays.py                 # rebuild every replay
    uv run python scripts/make_replays.py list RUN_ID     # see a run's items, scores and cost

## File format (version 1)

Line 1 is a metadata object. Every later line is one agent event, in recorded order, exactly as
`tariffagent.agents.events` defines it (`run_start`, `fact_extracted`, `tool_call`, `tree_focus`,
`advocate_chunk`, `advocate_done`, `adjudicator_chunk`, `ruling`, `cost_update`, `error`). Each
event validates with `EventAdapter`. `t` is seconds since the run started, as recorded.

Metadata fields:

| field | meaning |
|---|---|
| `type` | always `"meta"` |
| `format` | `1` |
| `exhibit_id` | unique id, also the file name |
| `title`, `blurb` | docket title and one-line teaser |
| `description` | the product description the agent saw |
| `kind` | `"exhibit"`, `"objection"` or `"timemachine"` |
| `mystery` | `true` for Beat the Broker exhibits. The API removes `gold_code`, `gold_digits`, `ruling_id`, `ruling_date`, `reference_excerpt` and `outcome` from the listing; `GET /api/exhibits/{id}/reveal` returns them |
| `agent`, `arm`, `models` | `"single"` or `"multi"`, the eval arm (`A`, `D`, ...) and model ids from `run_start` |
| `pair` | exhibits with the same `pair` are the same product heard by different agents. The UI offers a single vs multi-agent toggle and cost comparison across a pair. Defaults to the item id |
| `order` | docket order |
| `objection_of`, `fact_change` | for `kind: "objection"`: the exhibit it rehears and the one fact that changed |
| `timemachine` | for `kind: "timemachine"`: `{code, rev_a, rev_b}` the time machine opens with |
| `placeholder`, `placeholder_note` | `true` when the model was scripted, not a real run. The UI labels these |
| `note` | any other caveat shown with the exhibit |
| `gold_code`, `gold_stale`, `ruling_id`, `ruling_date`, `reference_excerpt` | the reference answer from the dataset. ATLAS items have no ruling number, only the code and a summary |
| `outcome` | the agent's code and the exact-match flags from `scored.jsonl` |
| `recorded` | cost and size of the recorded run: dollars, tokens by kind, calls, cache hit rate, tool calls, API latency and wall time |
| `source` | `run_id`, `item_id`, dataset and traces path it came from |
| `generated_by`, `generated_at` | provenance. `make_replays.py` only deletes files it generated |

## Timing

Eval runs go through the Message Batches API, so recorded gaps can be minutes long, and
cache hits have none. The server re-times the stream: every gap is capped at 1.5 s
(`DEMO_MAX_GAP_S`), a few event types get a short minimum gap so the tree and cards can
animate, and long text chunks are split into short pieces so they appear to stream. The
pieces join back into the recorded text. Each streamed event carries the compressed time in
`t` and the recorded time in `t_orig`. The UI says that timing is compressed. `?speed=N` on
the page URL plays N times faster (tests use it).

## exhibits.json

Each entry names one item of one run:

    {"exhibit_id": "wool-coat", "run_id": "pilot-dev20-A", "item_id": "atlas_validation_00044",
     "title": "Women's wool coat", "mystery": true}

`run_id` reads `evals/runs/<run_id>/traces.jsonl`, `results.jsonl` and `scored.jsonl`. An entry
may instead give `traces` (a path to a traces file in the same format, with a sibling
`.results.jsonl`). Optional keys: `kind`, `mystery`, `pair`, `blurb`, `objection_of`,
`fact_change`, `timemachine`, `placeholder`, `placeholder_note`, `note`, `gold_code`,
`ruling_id`, `reference_excerpt`, `dataset`, `skip`. Dataset fields (description, gold code,
ruling id) come from `evals/datasets/*.jsonl` by item id.

## What is here now

- 13 exhibits from `pilot-dev20-A` (real Claude Sonnet 5.5 runs, single agent, arm A), 6 of them
  mystery exhibits and one time-machine case (vinyl tiles, whose ruling code 3918.10.10.00 was
  split after 2018).
- `handbag-leather` and `handbag-pvc-objection`: real recorded runs (Claude Sonnet 5.5 in the Claude Code
  session, real tools on the full corpus, every tool call logged and replayed;
  `sources/objection.traces.jsonl`, built by `scripts/trace_from_blind.py`). The PVC run is a fresh
  classification of the changed description, not a continuation of the cowhide run.
- `handbag-leather-multi`: **placeholder**. A scripted stand-in model drives the real multi-agent code
  and real tools on the fixture database, so the events have the right shape, but the reasoning is
  scripted, it cites no rulings, and the cost is zero. Regenerate the fixture sources with
  `uv run python scripts/make_replays.py record-fixture` (offline, no spend).

To replace the remaining placeholder, record a multi-agent run on the same item, point its entry in
`exhibits.json` at it, drop `placeholder`, and rebuild.
