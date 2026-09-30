# Case study: an agent that argues tariff codes on the record

## The problem

Every product imported into the United States needs a 10-digit HTS code. The code sets the duty, and in 2026 it also decides which Section 301, 232 and reciprocal tariffs stack on top. Brokers classify by applying six General Rules of Interpretation (GRI) in order, reading section and chapter notes that exclude whole groups of goods, and citing CBP rulings on similar products. Rulings get modified and revoked, and codes move between HTS revisions.

The published baseline is ATLAS (arXiv 2509.18400): on 200 CBP rulings, a fine-tuned LLaMA-3.3-70B got 40.0% of 10-digit codes right, GPT-5-Thinking 25%, Gemini-2.5-Pro-Thinking 13.5%.

## Why it is hard

- The answer depends on facts that descriptions often leave out: knit or woven, fiber shares, the value of a handbag, whether a part is used solely with one machine.
- The last 4 digits are statistical suffixes. Lines with the same label ("Boys'", "Other") sit under different parents.
- Precedent is only useful if it is on the same product with the same facts, and still in force.
- The benchmark's labels are noisy (see the error analysis below).

## Approach

1. **Data** (Phase 0): the current HTS tree with notes and nine past revisions, metadata for 218,847 CROSS rulings and full text for 44,139, a derived status for each ruling (in force, modified, revoked), and a crosswalk from old codes to current lines.
2. **MCP server**: eight typed, read-only tools. Corpus text is wrapped as untrusted data, and documents that address an AI model are flagged.
3. **Agent Skill**: the broker workflow as a reusable skill with worked examples from real rulings.
4. **Single agent** with a checked final step: the code must be a current 10-digit line, a parts provision must name the parts rule it applied, and citations must exist, not be flagged, and not be revoked without saying so. When a check fails, the agent gets one repair turn.
5. **Multi-agent court**: an orchestrator picks 2 to 3 candidate headings, cheap advocates argue for one heading each (read only), and one strong adjudicator writes the answer.
6. **Controlled study design**: single agent (A), single agent with a token budget matched to the court (B), a cheap model that can ask a strong model (C, "smart friend"), and the court (D), same tools, skill, prompts and items. Built and tested; the test-set runs of B, C and D did not fit the budget (see below).

## Results

Full test split (200 rulings):

<!-- results:headline -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| ATLAS fine-tuned LLaMA-3.3-70B (published) | paper | 40.0% | 57.5% | | | |
| GPT-5-Thinking (published in ATLAS) | paper | 25.0% | | | | |
| Gemini-2.5-Pro-Thinking (published in ATLAS) | paper | 13.5% | | | | |
| Zero-shot, no tools, all 200 | Claude Sonnet 5 | 21.3% [14.9, 27.6] | 53.0% [46.0, 60.0] | 62.0% [55.5, 68.5] | 13.5% | $0.0061 |
<!-- /results:headline -->

The agent on `subset_80` (80 test items, same items in every row):

<!-- results:subset -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Zero-shot, no tools | Claude Sonnet 5 | 22.7% [12.1, 33.3] | 51.2% [40.0, 62.5] | 53.8% [42.5, 65.0] | 15.0% | $0.0067 |
| TariffAgent single agent (API) | gpt-5-mini | 43.9% [31.8, 56.1] | 51.2% [40.0, 62.5] | 57.5% [46.2, 68.8] | 22.5% | $0.0077 |
| Zero-shot, no tools (in the Claude Code session) | Claude Sonnet 5.5 | 21.2% [12.1, 31.8] | 53.8% [42.5, 65.0] | 63.7% [52.5, 73.8] | 13.8% | $0 (no API spend) |
| TariffAgent single agent (in the Claude Code session) | Claude Opus 5.5 | 51.5% [39.4, 63.6] | 63.7% [52.5, 73.8] | 70.0% [60.0, 80.0] | 20.0% | $0 (no API spend) |
| TariffAgent single agent, no date limit (in the Claude Code session) | Claude Sonnet 5.5 | 45.5% [33.3, 57.6] | 57.5% [46.2, 67.5] | 62.5% [51.2, 72.5] | 8.8% | $0 (no API spend) |
| TariffAgent single agent, rulings limited to before each item's own date (in the Claude Code session) | Claude Sonnet 5.5 | 47.0% [34.8, 59.1] | 60.0% [48.8, 70.0] | 65.0% [53.8, 75.0] | 11.2% | $0 (no API spend) |
<!-- /results:subset -->

<!-- results:subset_diffs -->
| Comparison (paired, same items) | 10-digit | 6-digit |
|---|---|---|
| Agent (Claude in session) minus Claude Sonnet 5 zero-shot | +28.8 points [+16.7, +40.9], n=66 | +12.5 points [+1.2, +23.8], n=80 |
| Agent (Claude in session) minus agent on gpt-5-mini | +7.6 points [-3.0, +18.2], n=66 | +12.5 points [+2.5, +22.5], n=80 |
| Agent (Claude in session) minus Claude Sonnet 5.5 zero-shot (in session) | +30.3 points [+18.2, +43.9], n=66 | +10.0 points [+1.2, +18.8], n=80 |
| No-date-limit agent (Claude Sonnet 5.5, in session) minus Claude Sonnet 5.5 zero-shot (in session) | +24.2 points [+12.1, +36.4], n=66 | +3.8 points [-6.2, +12.5], n=80 |
| Date-limited agent (Claude Sonnet 5.5, in session) minus Claude Sonnet 5.5 zero-shot (in session) | +25.8 points [+13.6, +37.9], n=66 | +6.2 points [-1.2, +13.8], n=80 |
| Date-limited agent minus no-date-limit agent (same model, same items: the effect of the date limit) | +1.5 points [-7.6, +10.6], n=66 | +2.5 points [-3.8, +8.8], n=80 |
<!-- /results:subset_diffs -->

<!-- analysis:headline -->
What the numbers say:

- **Tools and precedent carry most of the gain.** On the same 80 test items the agent got 51.5% of 10-digit codes right. Claude Sonnet 5.5 with no tools, run the same blind way, got 21.2%, and Claude Sonnet 5 zero-shot got 22.7%. On the fresh set the gap is larger: 82.5% against 15.0%. Without tools, models often find the right heading but miss the last four digits, which need the actual tariff tree.
- **The model is not held fixed.** The tuned API agent ran on Claude Sonnet 5; the test-set agent is Claude Opus 5.5 in the session, and the no-tools control is Claude Sonnet 5.5 (the usage limit ruled out an Opus control). So these rows show that the agent design works, not how much comes from the model. The gap to the gpt-5-mini agent (+7.6 points at 10 digits) has an interval that crosses zero.
- **Why the fresh set scores higher.** Its descriptions come from the ruling's own facts, its labels are the ruling's own current codes (no stale codes, no multi-article mismatch), and recent rulings on similar goods exist. The answer rulings, and any later ruling that names them, are hidden from the tools. The tools can also hide every ruling dated after an item's own ruling (next bullet).
- **Citations hold up.** No invented rulings: 97.5% of 79 citations on the subset and 100% of 42 on the fresh set are valid, in-corpus rulings with the right status.
- **Source-ruling hiding and the date limit.** Checking the dates showed the first linker missed the answer ruling for 42 of the 80 subset items (ATLAS gold codes are sometimes wrong, and it only looked at rulings listing the gold code), so those rulings were visible to the tools. The Opus 5.5 subset run cited a candidate source ruling 12 times, so its 51.5% is probably somewhat inflated. A second linker searches the whole corpus (150 of 150 correct on the fresh set, where the answer is known), hides every candidate, and dates 76 of the 80 subset items. The tools now also hide rulings dated after the item's own (a per-request date the model never sees; for ambiguous items it is the earliest candidate date, which is conservative). Without the limit, the Sonnet 5.5 agent cited 42 later-dated rulings on 37 subset items; with it, none. Same model, same items: 47.0% with the limit against 45.5% without on the subset, 85.0% against 82.5% on the fresh set. Both gaps sit inside the intervals, so the limit costs nothing measurable. The Sonnet 5.5 rows are the clean comparison with the Sonnet 5.5 no-tools control (21.2% and 15.0%). The judges passed 62.2% of the date-limited subset answers and 92.5% of the fresh ones.
- **Reasoning, not just codes.** A reference-grounded judge passed 67.6% of the subset answers and 90.0% of the fresh answers (details in `docs/EVAL.md`).
- These are 80 items, not the 200 the published ATLAS numbers use, so they are not a like-for-like comparison with that paper.
<!-- /analysis:headline -->

Post-cutoff set (150 rulings dated 2026-07-01 or later; the agent ran on a fixed 40-item sample):

<!-- results:fresh -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Zero-shot, no tools, all 150 | Claude Sonnet 5 | 20.0% [14.0, 26.7] | 48.0% [40.0, 56.0] | 69.3% [61.3, 76.7] | 1.3% | $0.0060 |
| Zero-shot, no tools, the 40-item sample | Claude Sonnet 5 | 17.5% [7.5, 30.0] | 47.5% [32.5, 62.5] | 67.5% [52.5, 82.5] | 2.5% | $0.0060 |
| Zero-shot, no tools (in the Claude Code session), same 40 | Claude Sonnet 5.5 | 15.0% [5.0, 27.5] | 60.0% [45.0, 75.0] | 70.0% [55.0, 82.5] | 7.5% | $0 (no API spend) |
| TariffAgent single agent (in the Claude Code session), same 40 | Claude Opus 5.5 | 82.5% [70.0, 92.5] | 90.0% [80.0, 97.5] | 92.5% [82.5, 100.0] | 7.5% | $0 (no API spend) |
| TariffAgent single agent, no date limit (in the Claude Code session), same 40 | Claude Sonnet 5.5 | 82.5% [70.0, 92.5] | 82.5% [70.0, 92.5] | 85.0% [72.5, 95.0] | 2.5% | $0 (no API spend) |
| TariffAgent single agent, rulings limited to before each item's own date (in the Claude Code session), same 40 | Claude Sonnet 5.5 | 85.0% [72.5, 95.0] | 92.5% [82.5, 100.0] | 92.5% [82.5, 100.0] | 0.0% | $0 (no API spend) |

Paired, same 40 items, agent minus Claude Sonnet 5 zero-shot: 10-digit +65.0 points [+50.0, +80.0], n=40; 6-digit +42.5 points [+27.5, +57.5], n=40.

Paired, same 40 items, agent minus Claude Sonnet 5.5 zero-shot (in session): 10-digit +67.5 points [+52.5, +82.5], n=40; 6-digit +30.0 points [+15.0, +45.0], n=40.

Paired, same 40 items, date-limited agent (Claude Sonnet 5.5) minus Claude Sonnet 5.5 zero-shot (both in session): 10-digit +70.0 points [+55.0, +85.0], n=40; 6-digit +32.5 points [+20.0, +47.5], n=40.

Paired, same 40 items, date-limited agent minus no-date-limit agent (same model; the effect of the date limit): 10-digit +2.5 points [-10.0, +15.0], n=40; 6-digit +10.0 points [+2.5, +20.0], n=40.
<!-- /results:fresh -->

### Reasoning judge

<!-- results:judge -->
| Run | Judge pass rate | Pass when 10-digit correct | Fail when chapter wrong | Cohen's kappa, second judge | Raw agreement |
|---|---|---|---|---|---|
| Test subset (80), Opus 5.5 agent | 67.6% [56.8, 78.4] (n=74) | 90.3% (n=31) | 90.9% (n=11) | 0.64 | 83.8% (n=74) |
| Fresh set (40), Opus 5.5 agent | 90.0% [80.0, 97.5] (n=40) | 100.0% (n=33) | 100.0% (n=1) | 0.77 | 95.0% (n=40) |
| Test subset (80), date-limited Sonnet 5.5 agent | 62.2% [51.3, 73.0] (n=74) | 100.0% (n=28) | 100.0% (n=11) | 0.89 | 94.6% (n=74) |
| Fresh set (40), date-limited Sonnet 5.5 agent | 92.5% [82.5, 100.0] (n=40) | 100.0% (n=34) | 100.0% (n=1) | 0.72 | 95.0% (n=40) |
<!-- /results:judge -->

<!-- analysis:judge -->
The judge compares the agent's reasoning with CBP's own analysis and passes only when the same legal basis reaches the same heading. Two judges ran in the session (Claude Opus 5.5 and Claude Haiku 4.5). Kappa is 0.64 on the subset and 0.77 on the fresh set; the 14 disagreements are split between Haiku being too strict below the heading, Haiku trusting a noisy gold code, and Opus being stricter about which GRI carried the decision. A first Haiku pass that compared strings instead of reading was thrown away and rerun. Details in `docs/EVAL.md`.
<!-- /analysis:judge -->

### Claude agent on the dev split (prompt work, not a test result)

<!-- results:dev -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Single agent, prompt v0 (dev_100) | Claude Sonnet 5 | 40.2% [29.9, 50.6] | 55.0% [45.0, 65.0] | 62.0% [52.0, 72.0] | 20.0% | $0.0289 |
| Single agent, prompt v1.2 (first 40 of dev_100) | Claude Sonnet 5 | 41.7% [25.0, 58.3] | 60.0% [45.0, 75.0] | 65.0% [50.0, 80.0] | 22.5% | $0.0479 |
| Multi-agent (first 10 of dev_100) | Claude Haiku 4.5 + Claude Sonnet 5 | 57.1% [14.3, 85.7] | 80.0% [50.0, 100.0] | 90.0% [70.0, 100.0] | 10.0% | $0.1010 |
| Pilot (first 20 of dev_100) | Claude Sonnet 5.5 | 43.8% [18.8, 68.8] | 60.0% [40.0, 80.0] | 80.0% [60.0, 95.0] | 15.0% | $0.0365 |
<!-- /results:dev -->

3 of the 40 items in the v1.2 run failed because the Anthropic account hit its spend limit mid-run; they count as misses. The multi-agent row has 10 items, so its interval spans most of the range.

## Error analysis

I read all 59 failures of the Claude single agent on dev_100 and tagged each with one level and one cause (`evals/taxonomy/dev100-A.jsonl`, `evals/reports/dev100-A.taxonomy.json`).

| Cause | Failures |
|---|---|
| Gold questionable (14 of them are descriptions listing several different articles, with one article's code as the gold) | 18 |
| Should have abstained (a deciding fact is missing and the agent guessed) | 9 |
| Followed a precedent on different facts | 7 |
| Abstained because a deciding fact is missing | 6 |
| Misread a fact in the description | 5 |
| Misapplied a GRI (mostly essential character) | 5 |
| Statistical suffix under the wrong parent | 2 |
| Missed a note | 2 |
| Abstained although it could answer | 2 |
| Relied on a ruling that predates the current suffixes | 1 |
| The right heading never surfaced | 1 |
| Malformed final answer | 1 |

What changed because of it (prompt v1.2, tuned on dev only): a best-guess code even when abstaining, the first-named article for multi-article descriptions, navigating the 8-digit line before picking a suffix, and a stricter test for precedent. On the same 40 dev items v1.2 matched v0 within noise. The analysis mostly showed that 24 of the 59 "errors" (18 questionable labels, 6 missing facts) are about the data, not the reasoning.

## Multi-agent vs single agent

The court was built and runs end to end: an orchestrator, parallel read-only advocates and one adjudicator, with typed events for the demo and a batched path that runs all advocates in the same Message Batch. On 10 dev items it scored higher than the single agent on the same items, at about twice the cost per item after the cost cuts (dev table above). Ten items cannot separate the two: the interval spans most of the range.

The planned controlled study (A single, B single with the court's token budget, C smart friend, D court, on the 80-item subset) did not run: the API budget ran out first. Arm B is the important control, because without it a win for D only shows that more tokens help. The harness supports all four arms (`--arm B --token-budget N`, `--arm C`, `--arm D`) and the runs resume from the response cache, so the study is one command per arm once there is a budget.

## Cost

<!-- results:cost -->
| | USD |
|---|---|
| Paid API spend, whole project | $13.34 |
| Same calls at list price, no caching, no batch discount | $39.71 |
| Saving from prompt caching and the Batch API | 66.4% |
| Share of input tokens read from the prompt cache | 81.4% |
| Blind test and fresh runs, and judging (in the Claude Code session) | $0 API spend |
<!-- /results:cost -->

- Prompt caching: a static prefix (tools, role, skill, GRI text) of about 7,400 tokens, a second breakpoint at the end of the conversation, and a 1-hour TTL for batch runs.
- The biggest single saving came from reading the bill. Requests inside one Message Batch run concurrently, so each paid its own cache write for the same prefix. One interactive "pre-warm" call per batch now writes it once. On the first round of the dev run, cost per request fell from $0.0109 (80 requests, before) to $0.0021 (100 requests, after), and 1-hour cache writes fell from 399,371 to 21,021 tokens (`evals/reports/caching_prewarm.json`).
- `max_tokens=0` pre-warming is refused together with structured output, and the output schema is part of the cached prefix, so the pre-warm asks for one token.
- The multi-agent court cost $0.153 per item in the first live check. Moving each advocate's heading out of the system prompt (so they share one cache entry), fewer and shorter advocates, and dropping full ruling texts brought it to $0.101.

## What the budget limited, and how the project finished anyway

The paid budget ($13.34) covered building, tuning, the dev analysis and the zero-shot baselines. The Anthropic account limit stopped a dev run twice. Free alternatives were tried in order: GitHub Models (the endpoint only answered "OK"), a local open-weights model (worked, but overheated the laptop), Hugging Face Jobs on included credits (built and dry-run tested, but the month's credit was already used), and Mistral's free tier (no longer offered to new organizations). The test-set agent run was finally done blind by Claude Opus 5.5 inside the Claude Code session, which the user's plan already covers: the same tools behind the MCP server with evaluation rulings hidden, the same skill and checks, a descriptions-only input file, and the same scorer. That run answers "does the agent design work on the test set". It is a different model from the Sonnet 5 API agent tuned on dev, and it is labeled that way everywhere. The same approach produced the fresh-set run, the no-tools controls (Claude Sonnet 5.5, after a usage limit stopped an Opus control part way) and both reasoning judges.

## What comes next

- Run the Claude agent (A and D) on the test split when a budget exists; every piece is in place and the response cache makes it resumable.
- Rerun the Opus 5.5 agent with the second source-ruling linker and the date limit (it needs usage headroom), so the main row and the clean comparison use the same model.
- Ask-for-facts as a first-class product mode: most wrong answers on well-labeled items traced to facts the description never gave.
- A cleaner benchmark: split multi-article rulings into one item per article.
- Ruling status from ruling text is right about 80% of the time on held-out cases. A small labeled set and a classifier would do better than the regex heuristic.
