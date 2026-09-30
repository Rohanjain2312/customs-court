#!/usr/bin/env bash
# Runs inside a Hugging Face Job (image vllm/vllm-openai). Paid from the PRO plan's included
# compute credits; the account has no payment method, so it cannot be billed beyond them.
#
# 1. Pull the private bundle (code + frozen data) and any earlier job state (response cache).
# 2. Serve two open-weights models with vLLM on the one GPU:
#      Qwen/Qwen3.6-35B-A3B-FP8  as local-qwen3.6-35b-a3b  (strong tier, :8081)
#      Qwen/Qwen3.5-4B           as local-qwen3.5-4b       (cheap tier, :8082)
# 3. Run the eval steps in JOB_PLAN, in order, until JOB_DEADLINE_MIN.
# 4. Sync state (cache, runs, reports, ledger, logs) back to the repo every 2 minutes and at the
#    end, so a job that stops early loses nothing: the next job resumes from the cache.
set -uo pipefail
REPO="${BUNDLE_REPO:-rohanjain2312/customs-court-evaljobs}"
TAG="${JOB_TAG:-job}"
PLAN="${JOB_PLAN:-check}"
DEADLINE_MIN="${JOB_DEADLINE_MIN:-40}"
START=$(date +%s)
W="${WORK_DIR:-/work}"
mkdir -p "$W" && cd "$W"
log() { echo "[$(date -u +%H:%M:%S) +$(( ($(date +%s) - START) / 60 ))m] $*"; }
left_min() { echo $(( DEADLINE_MIN - ($(date +%s) - START) / 60 )); }

log "pull bundle and earlier state"
python3 - <<PY
from huggingface_hub import snapshot_download
snapshot_download("$REPO", repo_type="dataset", local_dir="$W/hf", allow_patterns=["bundle/*", "results/gpu*/state.tar.gz"])
PY
[ -f hf/bundle/code.tar.gz ] || { log "bundle download failed"; exit 1; }
tar xzf hf/bundle/code.tar.gz -C "$W"
mkdir -p data/index data/cache evals/runs evals/reports logs
cp hf/bundle/data/*.sqlite hf/bundle/data/*.json data/ 2>/dev/null
cp hf/bundle/data/index/* data/index/
for s in hf/results/gpu*/state.tar.gz; do
  [ -f "$s" ] && tar xzf "$s" -C "$W" --exclude='logs/*' --exclude='data/ledger.jsonl' && log "restored $s"
done
: > data/ledger.jsonl

log "install harness (own venv, sees the image's torch)"
python3 -m venv --system-site-packages ${VENV_DIR:-/opt/ta}
# CPU torch first, so sentence-transformers does not pull a 2.5 GB CUDA build (query embeddings run on CPU).
${VENV_DIR:-/opt/ta}/bin/python -c "import torch" 2>/dev/null || \
  ${VENV_DIR:-/opt/ta}/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu > logs/pip.log 2>&1
${VENV_DIR:-/opt/ta}/bin/pip install -q "pydantic-settings==2.15.0" "typer==0.27.2" "rich==15.0.0" python-dotenv \
  "mcp==2.2.0" "anthropic[bedrock,vertex]==1.9.0" "openai==3.20.0" "sentence-transformers==6.1.0" \
  "faiss-cpu==1.15.1" pypdf beautifulsoup4 sse-starlette fastapi uvicorn pytest >> logs/pip.log 2>&1 || { log "pip failed"; tail -20 logs/pip.log; }
${VENV_DIR:-/opt/ta}/bin/pip install -q --no-deps -e . >> logs/pip.log 2>&1 || { log "install failed"; tail -20 logs/pip.log; exit 1; }
TA=${VENV_DIR:-/opt/ta}/bin/tariffagent

export DATA_DIR="$W/data" USE_VECTORS=true OFFLINE=false PHASE=open
export REASONER_MODEL=local-qwen3.6-35b-a3b ADVOCATE_MODEL=local-qwen3.5-4b JUDGE_MODEL=local-qwen3.6-35b-a3b
export LOCAL_ENDPOINTS="local-qwen3.6-35b-a3b=http://127.0.0.1:8081/v1,local-qwen3.5-4b=http://127.0.0.1:8082/v1"
export BUDGET_USD_TOTAL=0 TOOLS_PARALLEL=true

sync_state() {
  tar czf /tmp/state.tar.gz data/cache evals/runs evals/reports evals/taxonomy data/ledger.jsonl logs 2>/dev/null
  python3 -c "
from huggingface_hub import HfApi
HfApi().upload_file(path_or_fileobj='/tmp/state.tar.gz', path_in_repo='results/$TAG/state.tar.gz',
    repo_id='$REPO', repo_type='dataset', commit_message='state $TAG')" >/dev/null 2>&1 && log "synced state"
}
( while true; do sleep 120; sync_state; done ) &
SYNC_PID=$!

if [ "$PLAN" = "check" ]; then
  log "CPU check: offline tests and smoke eval"
  # Recorded fixtures were made with the Claude model ids.
  export REASONER_MODEL=claude-sonnet-5 ADVOCATE_MODEL=claude-haiku-4-5 JUDGE_MODEL=claude-haiku-4-5
  (cd "$W" && OFFLINE=true USE_VECTORS=false ${VENV_DIR:-/opt/ta}/bin/python -m pytest -q -m "not live" -p no:cacheprovider tests 2>&1 | tail -5) | tee logs/check.log
  (OFFLINE=true $TA eval smoke 2>&1 | tail -3) | tee -a logs/check.log
  ${VENV_DIR:-/opt/ta}/bin/python -c "from tariffagent.agents.runner import provider_for; print(type(provider_for('local-qwen3.6-35b-a3b')).__name__)" | tee -a logs/check.log
  ${VENV_DIR:-/opt/ta}/bin/python -c "
from tariffagent.mcp_server.tools.core import TariffTools
t = TariffTools(redact_eval=True); print('real-data tools ok', len(t.hts_search('leather handbag', 5).hits), len(t.cross_search('leather handbag').hits))" 2>&1 | tail -1 | tee -a logs/check.log
  vllm --version 2>&1 | tail -1 | tee -a logs/check.log
  kill $SYNC_PID; sync_state; exit 0
fi

serve() { # model name port mem maxlen
  vllm serve "$1" --served-model-name "$2" --host 127.0.0.1 --port "$3" --gpu-memory-utilization "$4" \
    --max-model-len "$5" --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser qwen3_coder \
    --reasoning-parser qwen3 --limit-mm-per-prompt '{"image":0,"video":0}' > "logs/vllm-$2.log" 2>&1 &
  for _ in $(seq 1 180); do
    curl -sf "http://127.0.0.1:$3/health" >/dev/null && { log "$2 ready"; return 0; }
    sleep 5
  done
  log "$2 failed to start"; tail -40 "logs/vllm-$2.log"; return 1
}
serve Qwen/Qwen3.6-35B-A3B-FP8 local-qwen3.6-35b-a3b 8081 "${MEM_A:-0.60}" 65536 || { sync_state; exit 1; }
serve Qwen/Qwen3.5-4B local-qwen3.5-4b 8082 "${MEM_B:-0.28}" 49152 || { sync_state; exit 1; }

run() { # run-id, then eval-run args
  local rid="$1"; shift
  if [ -f "evals/reports/$rid.json" ]; then log "skip $rid (done)"; return 0; fi
  local left; left=$(left_min)
  if [ "$left" -le 3 ]; then log "no time for $rid"; return 1; fi
  log "start $rid ($left min left)"
  timeout "$(( left - 2 ))m" $TA eval run --run-id "$rid" --mode interactive --concurrency "${CONC:-48}" ${EVAL_N:+--n $EVAL_N} "$@" \
    > "logs/$rid.log" 2>&1
  log "end $rid: $(grep -E 'acc10|usd/item' "logs/$rid.log" | tr '\n' ' ' | cut -c1-200)"
}

IFS=',' read -ra STEPS <<< "$PLAN"
for step in "${STEPS[@]}"; do
  case "$step" in
    A) run os-atlas200-A --dataset atlas_test_200 --arm A --phase open ;;
    D) run os-atlas200-D --dataset atlas_test_200 --arm D --phase open ;;
    freshA) run os-fresh150-A --dataset fresh_150 --arm A --phase open ;;
    Z) run os-atlas200-Z --dataset atlas_test_200 --arm Z --phase open ;;
    freshZ) run os-fresh150-Z --dataset fresh_150 --arm Z --phase open ;;
    B)
      bud=$(${VENV_DIR:-/opt/ta}/bin/python -c "import json;print(int(json.load(open('evals/reports/os-atlas200-D.json'))['metrics']['tokens_per_item']))" 2>/dev/null || echo 150000)
      run os-subset80-B --dataset atlas_test_200 --items-from subset_80 --arm B --token-budget "$bud" --max-turns 16 --phase open ;;
    C) run os-subset80-C --dataset atlas_test_200 --items-from subset_80 --arm C --phase open ;;
    objection)
      run os-demo-objection-A --dataset demo_objection --arm A --phase open
      run os-demo-objection-D --dataset demo_objection --arm D --phase open ;;
    ask) run os-subset80-A-ask --dataset atlas_test_200 --items-from subset_80 --arm A --ask-mode --phase open ;;
    judge)
      for r in os-atlas200-A os-atlas200-D os-fresh150-A atlas200-Z; do
        [ -f "evals/reports/$r.json" ] && [ ! -f "evals/reports/$r.judge.json" ] && [ "$(left_min)" -gt 3 ] && \
          timeout "$(( $(left_min) - 2 ))m" $TA eval judge "$r" --second-model local-qwen3.5-4b > "logs/judge-$r.log" 2>&1 && log "judged $r"
      done ;;
  esac
done
kill $SYNC_PID 2>/dev/null
sync_state
log "done"
