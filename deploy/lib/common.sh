# Shared helpers for deploy/*/build_and_validate.sh, deploy.sh and destroy.sh.
# Deploy-ready, not deployed. Source this file; do not run it.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="$HOME/.local/bin:$HOME/.local/opt/lima/bin:$PATH"

log() { printf '\n==> %s\n' "$*"; }
ok() { printf '    ok  %s\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

# Refuse unless the caller explicitly accepts cloud costs. Exit code 3 marks a refusal.
require_cost_opt_in() {
  if [ "${I_ACCEPT_CLOUD_COSTS:-}" != "yes" ]; then
    cat >&2 <<'EOF'

REFUSING: this script creates or deletes billable cloud resources.
Nothing was done. Read the estimate above and deploy/*/deploy.sh first.
To proceed on purpose, run it again with I_ACCEPT_CLOUD_COSTS=yes in the environment.
EOF
    exit 3
  fi
}

print_cost_estimate() {
  # stdlib-only Python, so it works before any project setup.
  python3 "$REPO_ROOT/deploy/cost_estimate.py" "$1"
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"
}

ensure_docker() {
  need docker
  if ! docker info >/dev/null 2>&1; then
    if command -v colima >/dev/null 2>&1; then
      log "docker daemon not reachable; starting colima"
      colima start >/dev/null 2>&1 || die "colima start failed"
    fi
    docker info >/dev/null 2>&1 || die "docker daemon not reachable"
  fi
}

# Wait until an MCP endpoint answers an initialize request (any HTTP status under 500).
wait_for_http() {
  local url="$1" tries="${2:-60}" code
  for _ in $(seq 1 "$tries"); do
    code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$url" \
      -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
      -d '{"jsonrpc":"2.0","id":0,"method":"ping"}' || true)
    if [ -n "$code" ] && [ "$code" != "000" ] && [ "$code" -lt 500 ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Disk size of a local image, as `docker image ls` reports it (uncompressed).
image_size() {
  docker image ls "$1" --format '{{.Size}}' | head -1
}
