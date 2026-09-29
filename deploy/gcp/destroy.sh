#!/usr/bin/env bash
# Destroy the TariffAgent Google Cloud deployment. Deploy-ready, never run by the project.
#
# Prints the cost estimate of what is running, then refuses unless I_ACCEPT_CLOUD_COSTS=yes.
# `make destroy-gcp` calls it. Reads resource names from deploy/gcp/.deployed.env
# (written by deploy.sh) and deletes: the Agent Runtime agent, the Cloud Run service,
# the Artifact Registry repository with its images, the staging bucket and the two
# service accounts. APIs stay enabled (enabling an API costs nothing).
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
cd "$REPO_ROOT"

print_cost_estimate gcp
require_cost_opt_in

need gcloud
[ -f deploy/gcp/.deployed.env ] || die "deploy/gcp/.deployed.env not found; nothing recorded to destroy"
# shellcheck disable=SC1091
source deploy/gcp/.deployed.env
G=(--project "$PROJECT" --quiet)

if [ -n "${AGENT_RESOURCE:-}" ]; then
  log "Agent Runtime agent"
  deploy/gcp/.venv/bin/python deploy/gcp/deploy_agent_runtime.py delete --resource "$AGENT_RESOURCE"
fi
log "Cloud Run service"
gcloud run services delete "$SERVICE_NAME" --region "$REGION" "${G[@]}" || true
log "Artifact Registry repository and images"
gcloud artifacts repositories delete "$AR_REPO" --location "$REGION" "${G[@]}" || true
log "staging bucket"
gcloud storage rm --recursive "$BUCKET" "${G[@]}" || true
log "service accounts"
for sa in tariffagent-mcp tariffagent-agent; do
  gcloud iam service-accounts delete "${sa}@${PROJECT}.iam.gserviceaccount.com" "${G[@]}" || true
done
rm -f deploy/gcp/.deployed.env
log "destroyed"
