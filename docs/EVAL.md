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

Distribution: 215,600 in force, 2,004 revoked, 1,254 modified, 759 unknown (mirror-only rulings with no CROSS metadata). Text-derived calls are only 117 of 219,617.

Accuracy against hand labels (I read the linking ruling text for every case; labels in `evals/status_check/`, scores in `evals/reports/ruling_status_accuracy.json`):

| Set | n | Accuracy | Notes |
|---|---|---|---|
| Check set, heuristic v1 | 50 | 96% | Stratified: 15 metadata revoked, 10 metadata modified, 10 text-derived, 5 reverse links, 10 in-force rulings cited by later HQ rulings. Both errors were text-derived. |
| Check set, v3 | 50 | 100% | In-sample: v2 and v3 were fixed after reading these cases. |
| Held-out after v2 | 20 | 85% | 13/15 text-derived, 4/5 correct drops. v3 came later, so partly in-sample. |
| Held-out after v3 froze | 10 | 70% | Text-derived only. The honest number for text-derived status. |

Plain summary: status from CROSS metadata and reverse links matched every sampled case (30/30), and in-force rulings that later rulings merely cite stayed in force (10/10). Status inferred from ruling text is right about 70 to 85% of the time. The main remaining error is direction: "NY K83213 was revoked by HQ W968273" can mark the revoking ruling as revoked. Tools say which method produced each status.

## Datasets

Defined in Phase 3 and 4 before any prompt work. See `evals/datasets/manifest.json`.

(Filled in as the phases complete.)
