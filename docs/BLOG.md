# Teaching an agent to argue tariff codes, on a $13 budget

*Draft.*

Every product that enters the United States needs a 10-digit code from the Harmonized Tariff Schedule. The code sets the duty. In 2026 it also decides which of the Section 301, 232 and reciprocal tariffs stack on top, so a wrong code is expensive. Customs brokers pick codes by applying six legal rules in order, reading the notes that exclude whole groups of goods, and citing earlier CBP rulings on similar products. Those rulings get modified and revoked, and the codes themselves move between revisions of the schedule.

I built Customs Court to see how far an agent gets at this, and to measure it honestly.

## What I built

- An MCP server with eight read-only tools over the tariff schedule and 44,139 CBP rulings, including whether each ruling is still in force.
- An Agent Skill that writes down the broker workflow, with worked examples from real rulings.
- A single agent with a checked final step, a multi-agent "court" (advocates argue for one heading each, a single adjudicator decides), and an eval harness with fixed datasets and confidence intervals.
- Deploy-ready AWS and Google Cloud packages that were validated locally and never deployed, because deploying costs money every month.
- A courtroom demo where you can object to a fact and watch the code change.

## Three things I learned

**Read the labels before you read the model.** I read all 59 failures on the dev split. Eighteen of them had a questionable gold answer. Fourteen of those were descriptions listing several different products ("hammers, picks and axes") while the benchmark kept one product's code. Another six were cases where the description lacked the one fact that decides the code. That changed what I tuned: always give a best guess, classify the first-named article, and treat missing facts as a product feature (ask for them) rather than a model bug.

**Read the bill.** Prompt caching was on from day one, but the first batch runs still cost more than expected. The Batch API runs requests concurrently, so every request in a batch paid to write the same 7,400-token prefix to the cache. One interactive call before each batch writes it once. Cost per request on the first round dropped about five-fold.

**Test the security story with a planted document.** A fixture ruling tells the model to ignore its instructions and answer 9999.99.99.99. The model ignored the fake code but still cited the planted ruling as "in force", which is half of what the attacker asked for. A simple deterministic flag on text that addresses an AI model, plus a citation check, closed that.

## Results

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

<!-- analysis:headline -->
<!-- /analysis:headline -->

## Multi-agent vs single agent

<!-- results:study_diffs -->
| Comparison (paired, same items) | 10-digit | 6-digit |
|---|---|---|
| B minus A | n/a | n/a |
| C minus A | n/a | n/a |
| D minus A | n/a | n/a |
<!-- /results:study_diffs -->

<!-- analysis:study -->
<!-- /analysis:study -->

## Doing it without a budget

The paid budget covered building, tuning and baselines. When it ran out, the remaining test runs moved to open-weights models served by vLLM on a Hugging Face Job, paid from the plan's included credits, with no payment method on file so nothing could be billed. The whole harness sits behind one provider interface, so the switch was a new adapter and a job script, not a rewrite. The trade-off is plain: the test-set agent numbers are for open models, not Claude.

Code and full write-up: the repository's `docs/CASE_STUDY.md`.
