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
| Zero-shot, no tools, all 200 | Claude Sonnet 5 | 21.3% [14.9, 27.6] | 53.0% [46.0, 60.0] | 62.0% [55.5, 68.5] | 13.5% | $0.0061 |
<!-- /results:headline -->

<!-- analysis:headline -->
On the same 80 test items, the agent working blind in the Claude Code session got 51.5% of 10-digit codes right. The same kind of model with no tools got 21.2%. On rulings issued after every model's training cutoff the gap is wider: 82.5% against 15.0%. Zero-shot models often land the right heading and then miss the last four digits, which need the actual tariff tree. The agent that ran on the test set is a different model from the one I tuned on dev, so this shows the design works, not how much the model adds. A second model graded the legal reasoning against CBP's own analysis and passed 67.6% of the subset answers.
<!-- /analysis:headline -->

The agent on the 80-item subset, all rows on the same items:

<!-- results:subset -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Zero-shot, no tools | Claude Sonnet 5 | 22.7% [12.1, 33.3] | 51.2% [40.0, 62.5] | 53.8% [42.5, 65.0] | 15.0% | $0.0067 |
| TariffAgent single agent (API) | gpt-5-mini | 43.9% [31.8, 56.1] | 51.2% [40.0, 62.5] | 57.5% [46.2, 68.8] | 22.5% | $0.0077 |
| Zero-shot, no tools (in the Claude Code session) | Claude Sonnet 5.5 | 21.2% [12.1, 31.8] | 53.8% [42.5, 65.0] | 63.7% [52.5, 73.8] | 13.8% | $0 (no API spend) |
| TariffAgent single agent (in the Claude Code session) | Claude Opus 5.5 | 51.5% [39.4, 63.6] | 63.7% [52.5, 73.8] | 70.0% [60.0, 80.0] | 20.0% | $0 (no API spend) |
<!-- /results:subset -->

## Doing it without a budget

The paid budget covered building, tuning and baselines. When it ran out I tried the free routes one by one: a local open-weights model (it worked, and overheated the laptop), Hugging Face Jobs on included credits (built and dry-run tested, but that month's credit was gone), and a free API tier (no longer offered). The run that finished the project was the plainest one: Claude working inside the Claude Code session, which my plan already covers, acting as the agent blind. It saw only the product descriptions, called the same tools through the MCP server with the answer rulings hidden, and was scored by the same code. It is a different model from the API agent I tuned, so it gets its own row.

Code and full write-up: the repository's `docs/CASE_STUDY.md`.
