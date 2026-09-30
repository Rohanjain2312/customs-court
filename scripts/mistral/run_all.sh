#!/usr/bin/env bash
# Run the remaining eval steps on Mistral's free "Experiment" plan. $0: free tier, rate-limited.
# Waits until the key has a non-zero rate limit, sets the request rate from the limit header,
# then runs the steps in priority order. Every response is cached, so a re-run resumes.
#   bash scripts/mistral/run_all.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
export PATH=~/.local/bin:$PATH
K=$(grep ^MISTRAL_API_KEY= .env | cut -d= -f2)
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

while true; do
  lim=$(curl -s -m 30 -D - -o /dev/null https://api.mistral.ai/v1/chat/completions -H "Authorization: Bearer $K" \
    -H "Content-Type: application/json" -d '{"model":"mistral-small-latest","messages":[{"role":"user","content":"OK"}],"max_tokens":1}' \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="x-ratelimit-limit-req-minute"{print $2}')
  [ -n "$lim" ] && [ "$lim" != "0" ] && break
  log "Mistral plan not active yet (limit ${lim:-?}/min); checking again in 2 minutes"
  sleep 120
done
RPS=$(python3 -c "print(max(0.2, min(5.0, ($lim - 1) / 60)))")
log "Mistral active: $lim requests/min -> $RPS requests/s"

export MISTRAL_RPS=$RPS PHASE=mistral TOOLS_PARALLEL=true
export REASONER_MODEL=mistral-medium-2604 ADVOCATE_MODEL=mistral-small-2603 JUDGE_MODEL=mistral-medium-2604
run() {
  local rid="$1"; shift
  [ -f "evals/reports/$rid.json" ] && { log "skip $rid (done)"; return; }
  log "start $rid"
  uv run tariffagent eval run --run-id "$rid" --mode interactive --concurrency "${CONC:-8}" "$@" > "data/logs/$rid.log" 2>&1
  log "end $rid: $(grep -E 'acc10|usd/item' "data/logs/$rid.log" | tr '\n' ' ' | cut -c1-160)"
}
run ms-atlas200-A --dataset atlas_test_200 --arm A --phase mistral
run ms-atlas200-D --dataset atlas_test_200 --arm D --phase mistral
run ms-fresh150-A --dataset fresh_150 --arm A --phase mistral
for r in ms-atlas200-A ms-atlas200-D ms-fresh150-A atlas200-Z; do
  [ -f "evals/reports/$r.json" ] && [ ! -f "evals/reports/$r.judge.json" ] && \
    uv run tariffagent eval judge "$r" --second-model mistral-small-2603 > "data/logs/judge-$r.log" 2>&1 && log "judged $r"
done
run ms-demo-objection-A --dataset demo_objection --arm A --phase mistral
run ms-demo-objection-D --dataset demo_objection --arm D --phase mistral
BUD=$(python3 -c "import json;print(int(json.load(open('evals/reports/ms-atlas200-D.json'))['metrics']['tokens_per_item']))" 2>/dev/null || echo 150000)
run ms-subset80-B --dataset atlas_test_200 --items-from subset_80 --arm B --token-budget "$BUD" --max-turns 16 --phase mistral
run ms-subset80-C --dataset atlas_test_200 --items-from subset_80 --arm C --phase mistral
run ms-atlas200-Z --dataset atlas_test_200 --arm Z --phase mistral
run ms-fresh150-Z --dataset fresh_150 --arm Z --phase mistral
run ms-subset80-A-ask --dataset atlas_test_200 --items-from subset_80 --arm A --ask-mode --phase mistral
log "all mistral steps done"
