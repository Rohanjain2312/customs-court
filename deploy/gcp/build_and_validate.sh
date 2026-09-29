#!/usr/bin/env bash
# Build and validate the GCP package locally. Deploy-ready, not deployed.
# Called by `make build-deploy-gcp`. Talks to no cloud account and calls no model API.
#
# Steps:
#   1. Stage the fixture data (12 MB) into deploy/.build.
#   2. docker build the MCP image for linux/amd64 (Cloud Run runs x86_64 images).
#   3. Run it with PORT=8080 as Cloud Run would; call every tool (deploy/aws/mcp_check.py).
#   4. MCP part of deploy/smoke_test.py (5 fixed products).
#   5. Check service.yaml: parses, no public invoker, port and probes consistent.
#   6. Build the isolated ADK venv if missing, write the prompt assets, and run the ADK
#      agent tree locally against the MCP container with scripted models.
# Exits non-zero on the first failure.
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
cd "$REPO_ROOT"

IMAGE=tariffagent-mcp:gcp-local
NAME=tariffagent-gcp-mcp
PORT_LOCAL=${MCP_PORT:-18800}
ADK_VENV=deploy/gcp/.venv

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

need uv
need curl
ensure_docker

log "1. stage fixture data"
uv run python scripts/export_deploy_data.py --fixture

log "2. build the amd64 MCP image"
docker build --platform linux/amd64 -f deploy/gcp/Dockerfile -t "$IMAGE" .
arch=$(docker image inspect "$IMAGE" --format '{{.Architecture}}')
[ "$arch" = "amd64" ] || die "$IMAGE is $arch, Cloud Run needs amd64 (x86_64)"
ok "$IMAGE amd64, $(image_size "$IMAGE")"

log "3. run it like Cloud Run (PORT=8080) and call every tool"
cleanup
docker run -d --name "$NAME" --platform linux/amd64 -e PORT=8080 \
  -p "127.0.0.1:${PORT_LOCAL}:8080" "$IMAGE" >/dev/null
wait_for_http "http://127.0.0.1:${PORT_LOCAL}/mcp" 180 || { docker logs "$NAME" | tail -30; die "MCP container did not start"; }
ok "MCP container answers on 127.0.0.1:${PORT_LOCAL}/mcp"
uv run python deploy/aws/mcp_check.py "http://127.0.0.1:${PORT_LOCAL}/mcp" --fixture --redacted

log "4. smoke test, MCP part only (no model calls)"
uv run python deploy/smoke_test.py --mcp-url "http://127.0.0.1:${PORT_LOCAL}/mcp" --mcp-auth none

log "5. check service.yaml"
uv run python - <<'EOF'
import re, sys, yaml
text = open("deploy/gcp/service.yaml").read()
svc = yaml.safe_load(text)
assert svc["kind"] == "Service" and svc["apiVersion"] == "serving.knative.dev/v1"
spec = svc["spec"]["template"]["spec"]
c = spec["containers"][0]
assert c["ports"][0]["containerPort"] == 8080, "container port must match the image's PORT"
assert c["startupProbe"]["tcpSocket"]["port"] == 8080
ann = svc["spec"]["template"]["metadata"]["annotations"]
assert ann["autoscaling.knative.dev/minScale"] == "0", "minScale must be 0 (scale to zero)"
assert ann["run.googleapis.com/cpu-throttling"] == "true", "request-based billing expected"
assert not re.search(r"allUsers|allAuthenticatedUsers", text.replace("never to all users", "")), "public access found"
print("    ok  service.yaml parses; port 8080, minScale 0, request-based billing, no public invoker")
EOF
if grep -nE -- '--member[= ]"?(allUsers|allAuthenticatedUsers)' deploy/gcp/deploy.sh; then
  die "deploy.sh grants public access"
fi
ok "deploy.sh grants run.invoker to the agent service account only"

log "6. ADK agent: local run against the MCP container, scripted models"
if [ ! -x "$ADK_VENV/bin/python" ]; then
  uv venv "$ADK_VENV" --python 3.12
fi
uv pip install --python "$ADK_VENV/bin/python" -q -r deploy/gcp/requirements.txt
DATA_DIR=deploy/.build/agent_data uv run python deploy/gcp/build_assets.py
"$ADK_VENV/bin/python" deploy/gcp/local_validation/run_local_adk.py "http://127.0.0.1:${PORT_LOCAL}/mcp" 2> >(grep -vE "UserWarning|check_feature_enabled|Skipping missing token usage|_build_declaration|mTLS" >&2)

log "image size (uncompressed, as reported by docker)"
echo "    $IMAGE $(image_size "$IMAGE")"
log "GCP package validated locally. Nothing was deployed."
