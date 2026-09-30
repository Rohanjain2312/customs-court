# Evaluation

This file records how the data was built, what each dataset is, how scoring works, and what the limits are. Results live in `evals/reports/`.

## Data sources and their limits

### HTS (USITC)
- Current tree: release `2026HTSRev20` (released 2026-09-23, effective 2026-09-28) from the USITC `exportList` endpoint. 35,805 rows, 19,949 ten-digit statistical lines. Every row carries its revision id.
- Notes: 98 chapter notes and 22 section notes from the USITC notes endpoints (HTML converted to text), and the General Rules of Interpretation from the USITC PDF.
- Past revisions for the time machine and `hts_revision_diff`: basic editions 2018 through 2026 from the USITC archive JSON files. Mid-year revisions before 2026 are not loaded.

### ATLAS benchmark
- The official Hugging Face repo `flexifyai/cross_rulings_hts_dataset_for_tariffs` returned "Repository not found" on 2026-09-28.
- We use the public mirror `Dayanand314Krishna/cross_rulings_hts_dataset_for_tariffs`. Its card is the Flexify.AI card and its split sizes match the paper (18,254 train, 200 validation, 200 test). The test split is used intact.
- ATLAS items have no ruling ids. We link each test and validation item to its likely source ruling: candidates are all CROSS rulings that list the gold code, scored by IDF-weighted word overlap between the item description and the ruling subject (plus text when held). Median link score is 0.60 on the test split. The top match and near ties (up to 5 per item) are redacted in `--redact-eval` mode: 307 ruling ids for `atlas_test_200`.

### CROSS rulings
- Metadata (date, collection, subject, codes, and the `modifiedBy`, `revokedBy`, `modifies`, `revokes` cross references) for 218,847 rulings, harvested month by month from the CROSS JSON search API at about one request per second with every page cached on disk. CROSS reported 221,876 searchable rulings on 2026-09-28, so coverage is 98.6%. The gap is most likely rulings without a usable date.
- Full text comes from two places:
  1. A community mirror on Hugging Face (`orlandowhite/hts-cross-rulings`, 54,558 rulings, 2000-01 to 2025-08). **The mirror's ruling ids do not always match its texts.** For example, the text stored under `963787` is ruling `I85020`. We keep a mirror text only when we can verify it (its own id in the header, another known id in the header whose CROSS codes appear in the text, or CROSS codes and subject words that match). That keeps 40,223 texts and drops 14,298. A spot check against CROSS of 30 kept texts: every one CROSS returned matched at word-set Jaccard 0.97 or higher; 7 ids had no CROSS detail page (HTTP 404 on `/api/ruling/<id>` even though CROSS search lists them). See `evals/reports/mirror_spotcheck.json`.
  2. CROSS directly, for every ruling dated 2025-07-01 or later (3,916 rulings), which covers the fresh evaluation set.
- robots.txt on rulings.cbp.gov returned 404 on 2026-09-28. We still rate limit and cache.

### Code drift and the crosswalk
- A gold code is `exact` when the 10-digit line exists today. Otherwise we map it when a clean mapping exists: the same description under the same 6-digit subheading in the latest past edition we hold (`desc_match`), or an 8-digit line that now has exactly one statistical suffix (`single_child`). Everything else is `code_stale`.
- `atlas_test_200`: 168 exact, 6 `desc_match`, 1 `single_child`, 2 eight-digit golds, 23 stale (11.5%). Stale items are scored at 6 digits and reported separately.
- Across the text corpus, 29.5% of distinct 10-digit codes cited by rulings are stale today, which is why tools show the current tree and `hts_revision_diff`.

## Ruling status (`in_force | modified | revoked | unknown`)

Derived in `src/tariffagent/data/status.py` from, in order: CROSS metadata on the ruling, reverse links from rulings that list it in `revokes` or `modifies`, and sentences in later HQ ruling texts ("NY N123456 is hereby revoked"). Proposed actions and negated or denied revocations are skipped.

Distribution after the text fetch finished and the corpus was frozen (2026-09-29): 215,556 in force, 2,030 revoked, 1,267 modified, 277 unknown (mirror-only rulings with no CROSS metadata). By method: 3,049 from CROSS metadata, 86 from reverse links, 162 from later ruling text, 215,556 with no signal (in force by default).

Accuracy against hand labels (I read the linking ruling text for every case; labels in `evals/status_check/`, scores in `evals/reports/ruling_status_accuracy.json`). The labeled sets were re-scored against the frozen corpus, where more HQ texts are present than when the heuristic was written:

| Set | n | Accuracy | Notes |
|---|---|---|---|
| Check set, heuristic v1 | 50 | 96% | Stratified: 15 metadata revoked, 10 metadata modified, 10 text-derived, 5 reverse links, 10 in-force rulings cited by later HQ rulings. Both errors were text-derived. |
| Check set, v3, frozen corpus | 50 | 98% | In-sample: v2 and v3 were fixed after reading these cases. One text-derived miss (817268). |
| Held-out after v2, frozen corpus | 20 | 90% | 14/15 text-derived, 4/5 correct drops. v3 came later, so partly in-sample. |
| Held-out after v3 froze, frozen corpus | 10 | 80% | Text-derived only. The honest number for text-derived status. It was 70% before the rest of the texts arrived. |

Plain summary: status from CROSS metadata and reverse links matched every sampled case (30/30), and in-force rulings that later rulings merely cite stayed in force (10/10). Status inferred from ruling text is right about 80 to 90% of the time on held-out cases (n = 10 and 20, so the intervals are wide). The main remaining error is direction: "NY K83213 was revoked by HQ W968273" can mark the revoking ruling as revoked. Tools say which method produced each status.

## Datasets

Defined in Phases 3 and 4 before any prompt work. Each has a sha256 in `evals/datasets/manifest.json`, and `load_dataset` refuses a file that does not match.

| Dataset | Size | Source | Use |
|---|---|---|---|
| `atlas_test_200` | 200 | ATLAS published test split (mirror of the ATLAS Hugging Face dataset) | reported results, direct comparison with the paper |
| `dev_100` | 100 | seeded sample of the ATLAS validation split | prompt work and error analysis only, never reported as a result |
| `fresh_300` | 300 | CROSS rulings dated 2026-07-01 to 2026-09-11 with one 10-digit code; description cut from the ruling's facts by a fixed rule that drops any sentence mentioning a code, heading or classification | post-cutoff set |
| `fresh_150` | 150 | seeded sample of `fresh_300`, to fit the budget | reported separately from ATLAS |
| `subset_80` | 80 | `atlas_test_200` stratified by product type and number of plausible headings | multi-agent study arms |
| `demo_objection` | 2 | hand-written leather and PVC handbag pair | demo only |

Every run uses `--redact-eval`: each golden ruling, and any later ruling that names it, is hidden from every tool.

## Metrics

- Exact match at 10, 8, 6 and 4 digits. Stale golds (the code no longer exists) are scored at 6 digits. 8-digit golds are scored at 8.
- Abstain rate, accuracy when answering, and a coverage vs accuracy curve (by confidence).
- Expected calibration error of the stated confidence.
- Citation validity: the cited ruling exists in the corpus and its derived status.
- Reasoning: a binary, reference-grounded judge. It sees the CBP ruling's own analysis and passes only when the same legal reason reaches the same heading. It is validated by a programmatic proxy (right at 10 digits should mostly pass, wrong chapter should fail) and by agreement with a second judge (Cohen's kappa).
- Cost per item, tokens per item, tool calls per item, cache hit rate, and p50 and p95 latency for interactive runs.
- 95% bootstrap intervals everywhere. A difference whose interval crosses zero is reported as within noise.

## Results

Test split (`atlas_test_200`):

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

Post-cutoff set (`fresh_150`):

<!-- results:fresh -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Zero-shot, no tools | Claude Sonnet 5 | 20.0% [14.0, 26.7] | 48.0% [40.0, 56.0] | 69.3% [61.3, 76.7] | 1.3% | $0.0060 |
| Zero-shot, no tools | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| TariffAgent single agent (A) | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
<!-- /results:fresh -->

Multi-agent study (`subset_80`, every arm on the same 80 items):

<!-- results:study -->
| Arm | Models | 10-digit | 6-digit | Tokens per item | Tool calls per item | Cost per item |
|---|---|---|---|---|---|---|
| A single agent | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| B single agent, token budget matched to D | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| C smart friend (cheap model asks the strong one) | Qwen3.5-4B (open weights) + Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| D multi-agent | Qwen3.5-4B (open weights) + Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| A with ask-for-facts mode | Qwen3.6-35B-A3B (open weights) | not run yet | | | | |
| A on another vendor (provider comparison) | gpt-5-mini | 43.9% [31.8, 56.1] | 51.2% [40.0, 62.5] | 65,307 | 6.25 | $0.0077 |
<!-- /results:study -->

<!-- results:study_diffs -->
| Comparison (paired, same items) | 10-digit | 6-digit |
|---|---|---|
| B minus A | n/a | n/a |
| C minus A | n/a | n/a |
| D minus A | n/a | n/a |
<!-- /results:study_diffs -->

Claude agent on dev (prompt work only):

<!-- results:dev -->
| System | Model | 10-digit | 6-digit | 4-digit | Abstain | Cost per item |
|---|---|---|---|---|---|---|
| Single agent, prompt v0 (dev_100) | Claude Sonnet 5 | 40.2% [29.9, 50.6] | 55.0% [45.0, 65.0] | 62.0% [52.0, 72.0] | 20.0% | $0.0289 |
| Single agent, prompt v1.2 (first 40 of dev_100) | Claude Sonnet 5 | 41.7% [25.0, 58.3] | 60.0% [45.0, 75.0] | 65.0% [50.0, 80.0] | 22.5% | $0.0479 |
| Multi-agent (first 10 of dev_100) | Claude Haiku 4.5 + Claude Sonnet 5 | 57.1% [14.3, 85.7] | 80.0% [50.0, 100.0] | 90.0% [70.0, 100.0] | 10.0% | $0.1010 |
| Pilot (first 20 of dev_100) | Claude Sonnet 5.5 | 43.8% [18.8, 68.8] | 60.0% [40.0, 80.0] | 80.0% [60.0, 95.0] | 15.0% | $0.0365 |
<!-- /results:dev -->

## Reasoning judge

<!-- analysis:judge -->
(Filled in from the judge reports.)
<!-- /analysis:judge -->

## Error analysis

All 59 failures of `dev100-A` were read and tagged (`evals/taxonomy/dev100-A.jsonl`). Distribution and what changed because of it: `docs/CASE_STUDY.md`, "Error analysis". The taxonomy lives in `src/tariffagent/evals/taxonomy.py`; four causes were added after reading (statistical suffix under the wrong parent, abstained for a missing fact, abstained although it could answer, malformed output).

## Which model produced which number

- Claude Sonnet 5: zero-shot baselines on both test sets, all dev agent runs after 2026-09-29.
- Claude Sonnet 5.5: the 20-item pilot only (the reasoner was switched to Sonnet 5 on 2026-09-29).
- gpt-5-mini: the provider comparison on `subset_80`.
- Qwen3.6-35B-A3B-FP8 and Qwen3.5-4B (open weights, Apache-2.0): the agent and study runs on the test sets, served by vLLM on a Hugging Face Job paid from included plan credits, with thinking off and Qwen's recommended sampling for that mode. Run ids start with `os-`.

