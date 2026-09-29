#!/usr/bin/env bash
# Build and validate the AWS package locally. Deploy-ready, not deployed.
# Called by `make build-deploy-aws`. Talks to no cloud account and calls no model API.
#
# Steps:
#   1. Stage the fixture data (12 MB) into deploy/.build.
#   2. docker build both ARM64 images (MCP server, agent).
#   3. Run the MCP container; call every tool with an MCP client (mcp_check.py),
#      including redaction, a platform-made Mcp-Session-Id and a Host header check.
#   4. MCP part of deploy/smoke_test.py (5 fixed products) against the container.
#   5. Run the agent container with AGENT_MODEL_MODE=scripted (BedrockProvider over an
#      in-process mock transport) against the MCP container; check /ping and /invocations.
#   6. terraform fmt -check, init -backend=false, validate.
# Exits non-zero on the first failure.
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
cd "$REPO_ROOT"

MCP_IMAGE=tariffagent-mcp:aws-local
AGENT_IMAGE=tariffagent-agent:aws-local
NET=tariffagent-aws-validate
MCP_NAME=tariffagent-aws-mcp
AGENT_NAME=tariffagent-aws-agent
MCP_PORT=${MCP_PORT:-18700}
AGENT_PORT=${AGENT_PORT:-18780}

cleanup() {
  docker rm -f "$MCP_NAME" "$AGENT_NAME" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

need uv
need curl
need terraform
ensure_docker

log "1. stage fixture data"
uv run python scripts/export_deploy_data.py --fixture

log "2. build ARM64 images"
docker build --platform linux/arm64 -f deploy/aws/Dockerfile -t "$MCP_IMAGE" .
docker build --platform linux/arm64 -f deploy/aws/Dockerfile.agent -t "$AGENT_IMAGE" .
for img in "$MCP_IMAGE" "$AGENT_IMAGE"; do
  arch=$(docker image inspect "$img" --format '{{.Architecture}}')
  [ "$arch" = "arm64" ] || die "$img is $arch, AgentCore needs arm64"
  ok "$img arm64, $(image_size "$img")"
done

log "3. run the MCP container and call every tool"
cleanup
docker network create "$NET" >/dev/null
# MCP_ALLOWED_HOSTS turns on the Host header check so it can be tested here.
docker run -d --name "$MCP_NAME" --network "$NET" --platform linux/arm64 \
  -p "127.0.0.1:${MCP_PORT}:8000" \
  -e MCP_ALLOWED_HOSTS="127.0.0.1:${MCP_PORT},localhost:${MCP_PORT},${MCP_NAME}:8000" \
  "$MCP_IMAGE" >/dev/null
wait_for_http "http://127.0.0.1:${MCP_PORT}/mcp" 90 || { docker logs "$MCP_NAME" | tail -30; die "MCP container did not start"; }
ok "MCP container answers on 127.0.0.1:${MCP_PORT}/mcp"
uv run python deploy/aws/mcp_check.py "http://127.0.0.1:${MCP_PORT}/mcp" --fixture --redacted \
  --allowed-host "127.0.0.1:${MCP_PORT}"

log "4. smoke test, MCP part only (no model calls)"
uv run python deploy/smoke_test.py --mcp-url "http://127.0.0.1:${MCP_PORT}/mcp" --mcp-auth none

log "5. run the agent container (scripted Bedrock stand-in) against the MCP container"
docker run -d --name "$AGENT_NAME" --network "$NET" --platform linux/arm64 \
  -p "127.0.0.1:${AGENT_PORT}:8080" \
  -e AGENT_MODEL_MODE=scripted -e MCP_AUTH=none -e "MCP_URL=http://${MCP_NAME}:8000/mcp" \
  "$AGENT_IMAGE" >/dev/null
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${AGENT_PORT}/ping" >/dev/null 2>&1 && break
  sleep 1
done
ping=$(curl -sf "http://127.0.0.1:${AGENT_PORT}/ping") || { docker logs "$AGENT_NAME" | tail -30; die "agent /ping failed"; }
[ "$ping" = '{"status":"Healthy"}' ] || die "unexpected /ping body: $ping"
ok "/ping -> $ping"
uv run python deploy/aws/agent_check.py "http://127.0.0.1:${AGENT_PORT}" || { docker logs "$AGENT_NAME" | tail -40; die "agent check failed"; }

log "6. terraform fmt, init -backend=false, validate (no plan, no apply)"
(
  cd deploy/aws/terraform
  terraform fmt -check -recursive
  terraform init -backend=false -input=false -no-color >/dev/null
  terraform validate -no-color
)

log "image sizes (uncompressed, as reported by docker)"
echo "    $MCP_IMAGE   $(image_size "$MCP_IMAGE")"
echo "    $AGENT_IMAGE $(image_size "$AGENT_IMAGE")"
log "AWS package validated locally. Nothing was deployed."
