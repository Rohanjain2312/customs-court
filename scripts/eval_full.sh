#!/usr/bin/env bash
# Every paid evaluation run, in the spend order from the plan (section 1).
# Spends money on the Anthropic and OpenAI APIs only, capped by BUDGET_USD_* in .env.
# Everything goes through the on-disk response cache, so a re-run of a finished
# step costs nothing and a crashed step resumes where it stopped.
set -euo pipefail
run() { uv run tariffagent eval run "$@"; }

# 1. Baseline on dev_100 (prompt work and error analysis only, never reported).
run --dataset dev_100 --arm A --mode batch --run-id dev100-A --phase baseline
# 2. Zero-shot baseline, no tools.
run --dataset atlas_test_200 --arm Z --mode batch --run-id atlas200-Z --phase baseline
# 3. Headline arms A and D on the ATLAS test split.
run --dataset atlas_test_200 --arm A --mode batch --run-id atlas200-A --phase headline
run --dataset atlas_test_200 --arm D --mode batch --run-id atlas200-D --phase headline
# 4. Fresh set (post training cutoff), reported separately.
run --dataset fresh_150 --arm A --mode batch --run-id fresh150-A --phase fresh
run --dataset fresh_150 --arm Z --mode batch --run-id fresh150-Z --phase fresh
# 5. Study arms on the stratified subset. B's budget matches D's mean tokens per item.
B_BUDGET=$(uv run python -c "import json;print(int(json.load(open('evals/reports/atlas200-D.json'))['metrics']['tokens_per_item']))")
run --dataset atlas_test_200 --items-from subset_80 --arm B --token-budget "$B_BUDGET" --max-turns 16 --mode batch --run-id subset80-B --phase study
run --dataset atlas_test_200 --items-from subset_80 --arm C --mode batch --run-id subset80-C --phase study
run --dataset atlas_test_200 --items-from subset_80 --arm A --ask-mode --mode batch --run-id subset80-A-ask --phase depth
run --dataset atlas_test_200 --items-from subset_80 --arm O --mode interactive --run-id subset80-O --phase provider
# 6. Judges and reports (judges spend a little; compare and taxonomy are offline).
uv run tariffagent eval judge atlas200-A
uv run tariffagent eval judge atlas200-D --no-second-judge
uv run tariffagent eval compare atlas_test_200 --runs A=atlas200-A,D=atlas200-D,Z=atlas200-Z --name headline_atlas200
