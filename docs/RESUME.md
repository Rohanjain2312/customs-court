# Resume bullets

Every figure below is in `evals/reports/` (checked by `scripts/number_audit.py`).

**Customs Court: an agent that classifies imports into 10-digit US tariff codes.** Python, MCP, Claude API, OpenAI API, FastAPI, React.

- Built an MCP server with eight read-only tools over the current US tariff schedule, nine past revisions and 44,139 CBP rulings, including whether each ruling is still in force, plus a reusable Agent Skill encoding the customs broker workflow.
- On 80 held-out benchmark items, the agent got 51.5% of 10-digit codes right, against 21.2% for a no-tools model on the same items. On rulings issued after the models' training cutoff it got 82.5%, against 15.0%. No invented citations.
- Built the eval harness: fixed datasets with checksums, hidden answer rulings, bootstrap intervals, a reference-grounded reasoning judge checked against a second judge (Cohen's kappa 0.64 and 0.77) and a programmatic proxy.
- Cut API cost by 66.4% against list price with prompt caching and the Batch API; found that batched requests each paid for the same cache write and fixed it with one pre-warm call, taking cost per request from $0.0109 to $0.0021.
- Read and tagged all 59 dev failures: 18 had a questionable benchmark label and 6 more lacked the fact that decides the code, which set the prompt changes.

One-line version:

> Built an MCP-based agent for US tariff classification that got 51.5% of 10-digit codes right on held-out benchmark items (a no-tools model: 21.2%), with a full eval harness and 66.4% lower API cost from caching and batching.
