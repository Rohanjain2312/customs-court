#!/usr/bin/env bash
# Deploy TariffAgent to Google Cloud (Cloud Run MCP server + Vertex AI Agent Runtime).
# Deploy-ready, never run by the project.
#
# THIS CREATES BILLABLE GOOGLE CLOUD RESOURCES. It prints a cost estimate, then refuses
# unless I_ACCEPT_CLOUD_COSTS=yes is set. `make deploy-gcp` calls it.
#
# What it does, in order:
#   1. Enable the Run, Artifact Registry and Vertex AI APIs; create an Artifact Registry
#      repository, two service accounts and a staging bucket (idempotent).
#   2. Stage the real data and build and push the amd64 MCP image (VECTORS=1).
#   3. Deploy service.yaml to Cloud Run. Grant roles/run.invoker to the agent service
#      account only. The service is never public.
#   4. Deploy the ADK agent to Agent Runtime (deploy_agent_runtime.py), pointed at the
#      Cloud Run URL, with ID-token auth to the MCP server.
#   5. Write resource names to deploy/gcp/.deployed.env (gitignored) for destroy.sh.
#
# Needs: gcloud signed in to the target project, docker with buildx, uv, the ADK venv
# (deploy/gcp/.venv, created by build_and_validate.sh) and access to Claude on Vertex AI
# (enabled per model in Model Garden). Env: GOOGLE_CLOUD_PROJECT (required),
# REGION (default us-central1), IMAGE_TAG.
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
cd "$REPO_ROOT"

print_cost_estimate gcp
require_cost_opt_in

need gcloud
need uv
ensure_docker
PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${REGION:-us-central1}"
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo local)-$(date +%Y%m%d%H%M%S)}"
SERVICE_NAME=tariffagent-mcp
AR_REPO=tariffagent
MCP_SA="tariffagent-mcp@${PROJECT}.iam.gserviceaccount.com"
AGENT_SA="tariffagent-agent@${PROJECT}.iam.gserviceaccount.com"
BUCKET="gs://${PROJECT}-tariffagent-staging"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/tariffagent-mcp:${TAG}"
G=(--project "$PROJECT" --quiet)

log "1. APIs, repository, service accounts, staging bucket"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com "${G[@]}"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" "${G[@]}" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION" "${G[@]}"
for sa in tariffagent-mcp tariffagent-agent; do
  gcloud iam service-accounts describe "${sa}@${PROJECT}.iam.gserviceaccount.com" "${G[@]}" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$sa" --display-name "$sa" "${G[@]}"
done
# The agent calls Claude on Vertex AI.
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${AGENT_SA}" \
  --role roles/aiplatform.user --condition None "${G[@]}" >/dev/null
gcloud storage buckets describe "$BUCKET" "${G[@]}" >/dev/null 2>&1 ||
  gcloud storage buckets create "$BUCKET" --location "$REGION" --uniform-bucket-level-access "${G[@]}"

log "2. stage real data, build and push the amd64 MCP image"
uv run python scripts/export_deploy_data.py
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker buildx build --platform linux/amd64 --build-arg VECTORS=1 -f deploy/gcp/Dockerfile -t "$IMAGE" --push .

log "3. Cloud Run service (IAM invoker check on, no public access)"
RENDERED="$(mktemp)"
SERVICE_NAME="$SERVICE_NAME" REGION="$REGION" MCP_SERVICE_ACCOUNT="$MCP_SA" IMAGE="$IMAGE" USE_VECTORS=true \
  python3 -c 'import os,string,sys; sys.stdout.write(string.Template(open("deploy/gcp/service.yaml").read()).substitute(os.environ))' >"$RENDERED"
gcloud run services replace "$RENDERED" --region "$REGION" "${G[@]}"
gcloud run services add-iam-policy-binding "$SERVICE_NAME" --region "$REGION" \
  --member "serviceAccount:${AGENT_SA}" --role roles/run.invoker "${G[@]}" >/dev/null
RUN_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)' "${G[@]}")
echo "    Cloud Run URL: $RUN_URL (ID token required)"

log "4. ADK agent on Agent Runtime"
[ -x deploy/gcp/.venv/bin/python ] || die "deploy/gcp/.venv missing; run make build-deploy-gcp first"
DATA_DIR=deploy/.build/agent_data uv run python deploy/gcp/build_assets.py
OUT=$(deploy/gcp/.venv/bin/python deploy/gcp/deploy_agent_runtime.py create --project "$PROJECT" \
  --location "$REGION" --staging-bucket "$BUCKET" --service-account "$AGENT_SA" --mcp-url "${RUN_URL}/mcp")
echo "$OUT"
AGENT_RESOURCE=$(echo "$OUT" | sed -n 's/^created: //p')

log "5. record resource names"
cat >deploy/gcp/.deployed.env <<EOF
PROJECT=$PROJECT
REGION=$REGION
SERVICE_NAME=$SERVICE_NAME
AR_REPO=$AR_REPO
BUCKET=$BUCKET
AGENT_RESOURCE=$AGENT_RESOURCE
EOF
cat <<EOF

Smoke test (bills; model calls on Vertex AI):
  I_ACCEPT_CLOUD_COSTS=yes deploy/gcp/.venv/bin/python deploy/smoke_test.py --vertex-agent "$AGENT_RESOURCE"
Tear down with: I_ACCEPT_CLOUD_COSTS=yes make destroy-gcp
EOF
