# Walkthrough scripts

Two talk tracks and the questions that usually follow. Numbers are in `docs/CASE_STUDY.md` and come from `evals/reports/`; say them from there, not from memory.

## 5 minutes

1. **The problem (45 s).** Importers must give every product a 10-digit HTS code. The code sets the duty and which extra tariffs stack on top. Brokers do it with six legal rules, section and chapter notes, and CBP rulings that can be revoked. The published benchmark (ATLAS) shows even strong models get a quarter to two fifths of 10-digit codes right.
2. **What I built (60 s).** An MCP server with eight tools over the HTS and 44,139 CBP rulings, including whether each ruling is still in force. A reusable Agent Skill with the broker workflow. A single agent and a multi-agent "court" on top, and an eval harness with fixed datasets and confidence intervals.
3. **Demo (90 s).** `make replay`. Pick the leather handbag. The tree lights up as the agent navigates. The ruling panel shows the GRI path and the cited rulings with status badges. Click Objection, change the outer surface to PVC, and the code moves from 4202.21 to 4202.22. Then one Beat the Broker round.
4. **Results (60 s).** Read the headline table: published ATLAS baselines, the Claude zero-shot baseline, and the agent on the test set. Then the fresh set of rulings from after every model's training cutoff. Say what the intervals mean.
5. **What I learned (45 s).** A third of the dev failures were about the labels or missing facts, not the reasoning. The biggest cost win came from reading the bill: batch requests were each paying to cache the same prompt.

## 12 minutes

1. **Problem and stakes (1.5 min).** As above, plus why stale codes and revoked rulings matter.
2. **Data (1.5 min).** USITC HTS with nine past revisions; CROSS metadata for 218,847 rulings and full text for 44,139; a Hugging Face mirror whose ids did not match its texts, so only verified texts were kept; ruling status derived from cross-references and measured against hand labels.
3. **MCP and the skill (2 min).** One tool implementation served over stdio and stateless HTTP. `--redact-eval` hides the answer rulings. Untrusted-text wrapping and the planted prompt-injection ruling test: Sonnet 5 ignored the fake code but cited the planted ruling, which led to a deterministic flag and a citation check.
4. **The agent (2 min).** Tool loop with caps, structured output, prompt caching, the checked final step and repair turn, batch runner with the same episode code.
5. **Eval (2 min).** Datasets fixed before prompt work, dev-only tuning, 59 failures read and tagged, the multi-article label problem, bootstrap intervals, the judge and its second judge.
6. **Multi-agent (1.5 min).** The court's design (read-only advocates, one writer) and why arm B (same token budget) is the control that matters. It ran on 10 dev items only; say that plainly.
7. **Cost and constraints (1 min).** Caching savings, the pre-warm fix, the spend lock, the free routes that failed, and the blind in-session run that finished the evaluation.
8. **Deploy-ready packages (0.5 min).** AgentCore and Cloud Run designs validated locally, deploy scripts that refuse without an explicit opt-in.

## Likely questions, honest answers

- **Contamination?** Models may have seen older rulings. That is why a fresh set of rulings dated after every training cutoff is reported separately. The eval tools also hide the answer ruling and any later ruling that names it.
- **Stale codes?** 11.5% of ATLAS test golds no longer exist in today's HTS. They are scored at 6 digits and left out of the 10-digit column.
- **Why not fine-tune?** ATLAS already shows a fine-tuned 70B model. The point here is an agent that cites current law and precedent and checks status, which fine-tuning cannot keep current. A fine-tuned model could slot in behind the same provider interface.
- **Is the multi-agent result real?** Not yet shown. It ran on 10 dev items, where the interval spans most of the range, and the token-matched control (arm B) did not run. The harness does it with one command per arm once there is a budget.
- **Who produced the test-set agent numbers?** Claude Opus 5.5 inside the Claude Code session, blind: a descriptions-only input file, the same tools with answer rulings hidden, the same skill, checks and scorer. The paid API budget had run out. It is a different model from the Sonnet 5 API agent tuned on dev, so it is reported separately. The API agent on test is the next step.
- **Why is nothing deployed?** Deploying costs money every month. The packages are built and validated locally, with cost estimates, and the deploy scripts refuse to run without an explicit opt-in.
- **How good is the ruling status?** From CROSS metadata and reverse links it matched every sampled case. Inferred from ruling text it is right about 80% of the time on held-out cases, with small samples.
- **What would you do next?** Split multi-article rulings into clean items, make ask-for-facts a product mode, and run the Claude agent on test when there is budget.
