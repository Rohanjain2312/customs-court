#!/usr/bin/env bash
# Wait for the monthly credit refill, then run the GPU job and collect its results.
set -uo pipefail
cd "$(dirname "$0")/../.."
export PATH=~/.local/bin:$PATH
AT="${1:-2026-10-01 00:05}"
TARGET=$(date -j -u -f "%Y-%m-%d %H:%M" "$AT" +%s)
while [ "$(date -u +%s)" -lt "$TARGET" ]; do sleep 300; done
uv run python scripts/hf_job/push_bundle.py > data/logs/hfjob-push.log 2>&1

wait_job() {
  while true; do
    st=$(uv run python -c "from huggingface_hub import HfApi; print(HfApi().inspect_job(job_id='$1').status.stage)" 2>/dev/null)
    case "$st" in COMPLETED|ERROR|CANCELED|DELETED) echo "job $1 $st"; return 0 ;; esac
    sleep 30
  done
}

# 1. Cheap CPU check in the same image (offline tests, real-data tools, vLLM version).
c=$(uv run python scripts/hf_job/launch.py run --tag check1 --plan check --flavor cpu-upgrade --timeout 25m 2>&1)
echo "$c" | tail -2
CJ=$(echo "$c" | tail -1 | awk '{print $1}')
[ ${#CJ} -ge 20 ] || { echo "check launch failed"; exit 1; }
wait_job "$CJ"
uv run python scripts/hf_job/launch.py status "$CJ" --logs > data/logs/hfjob-check1-joblog.txt 2>&1
uv run python scripts/hf_job/launch.py fetch --tag check1
if ! grep -q "passed" data/logs/hfjob-check1/check.log || ! grep -q "real-data tools ok" data/logs/hfjob-check1/check.log; then
  echo "CHECK FAILED: not starting the GPU job"; exit 2
fi

# 2. The GPU job.
PLAN="${JOB_PLAN:-A,D,freshA,judge,objection,B,C,Z,freshZ,ask,judge}"
out=$(uv run python scripts/hf_job/launch.py run --tag gpu1 --plan "$PLAN" --flavor "${FLAVOR:-rtx-pro-6000}" --timeout "${TIMEOUT:-43m}" 2>&1)
echo "$out" | tail -2
JOB=$(echo "$out" | tail -1 | awk '{print $1}')
[ ${#JOB} -ge 20 ] || { echo "launch failed"; exit 1; }
wait_job "$JOB"
uv run python scripts/hf_job/launch.py status "$JOB" --logs > data/logs/hfjob-gpu1-joblog.txt 2>&1
uv run python scripts/hf_job/launch.py fetch --tag gpu1
