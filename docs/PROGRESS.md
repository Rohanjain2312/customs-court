# Progress

## Phase 0: Data foundation (2026-09-28)

Built
- HTS ingestion (`src/tariffagent/data/hts.py`): current release 2026HTSRev20 with revision id on every row, chapter and section notes, GRI text, and nine past basic editions (2018 to 2026).
- CROSS ingestion (`src/tariffagent/data/cross.py`): metadata for 218,847 rulings (98.6% of what CROSS reports), verified mirror texts (40,223), and direct CROSS texts for everything since 2025-07-01.
- ATLAS loader and ruling linker (`src/tariffagent/data/atlas.py`), with redaction rows for the test and validation splits.
- Crosswalk and `code_stale` (`src/tariffagent/data/crosswalk.py`).
- Ruling status derivation (`src/tariffagent/data/status.py`) with a hand-labeled 50-case check set and two held-out sets. Accuracy in `docs/EVAL.md`.
- Hybrid index (`src/tariffagent/index/search.py`): SQLite FTS5 plus local `BAAI/bge-small-en-v1.5` vectors, fused with reciprocal rank fusion.
- Budget-enforced spend ledger, on-disk response cache, config module.

How to run
- `make data` runs the whole pipeline (resumable, raw responses cached under `data/raw/`).
- `uv run tariffagent data status` prints counts, date ranges, stale-code rate and status distribution.

Tests passing
- `tests/test_data_parsing.py` (tree building, code helpers, notes HTML, ATLAS parsing, status text rules).

Unverified or open
- The CROSS full-text fetch for 2025-07 onward was still running at commit time (about 1,300 of 3,916 done). Re-run `make data` to finish; it resumes.
- The embedding index was still building at commit time.
- Mirror texts dropped for failing verification (14,298) are not replaced. Older rulings outside the verified set have metadata only.
- 1.4% of CROSS rulings are missing from the metadata harvest.
