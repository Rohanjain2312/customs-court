#!/usr/bin/env bash
# Deploy TariffAgent to Amazon Bedrock AgentCore. Deploy-ready, never run by the project.
#
# THIS CREATES BILLABLE AWS RESOURCES. It prints a cost estimate, then refuses unless
# I_ACCEPT_CLOUD_COSTS=yes is set. `make deploy-aws` calls it.
#
# What it does, in order:
#   1. Stage the real data (scripts/export_deploy_data.py) with the vector index.
#   2. terraform apply on the two ECR repositories only.
#   3. docker buildx build --platform linux/arm64 --push for both images (VECTORS=1).
#   4. terraform apply for everything else (runtimes, gateway, IAM, observability).
#      Terraform asks for approval unless AUTO_APPROVE=yes.
#   5. Print the endpoints and the smoke test command.
#
# Needs: AWS credentials for the target account (aws sts get-caller-identity works),
# terraform >= 1.9, docker with buildx, uv, and model access to Claude on Bedrock in
# the region. Optional env: AWS_REGION (default us-east-1), IMAGE_TAG, AUTO_APPROVE,
# TF_VAR_* for any variable in terraform/variables.tf (for example JWT inbound auth).
# State is local (deploy/aws/terraform/terraform.tfstate, gitignored). For shared use,
# add an S3 backend first.
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
cd "$REPO_ROOT"

print_cost_estimate aws
require_cost_opt_in

need aws
need terraform
need uv
ensure_docker

REGION="${AWS_REGION:-us-east-1}"
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo local)-$(date +%Y%m%d%H%M%S)}"
APPROVE=()
[ "${AUTO_APPROVE:-}" = "yes" ] && APPROVE=(-auto-approve)
export TF_VAR_i_accept_cloud_costs=yes TF_VAR_region="$REGION"

log "AWS identity"
aws sts get-caller-identity --output text

log "1. stage real data (with vector index)"
uv run python scripts/export_deploy_data.py

log "2. ECR repositories"
cd deploy/aws/terraform
terraform init -input=false
terraform apply ${APPROVE[@]+"${APPROVE[@]}"} -target=aws_ecr_repository.mcp -target=aws_ecr_repository.agent \
  -var "mcp_image_tag=$TAG" -var "agent_image_tag=$TAG"
MCP_REPO=$(terraform output -raw mcp_ecr_repository_url)
AGENT_REPO=$(terraform output -raw agent_ecr_repository_url)
cd "$REPO_ROOT"

log "3. build and push ARM64 images, tag $TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${MCP_REPO%%/*}"
docker buildx build --platform linux/arm64 --build-arg VECTORS=1 -f deploy/aws/Dockerfile \
  -t "$MCP_REPO:$TAG" --push .
docker buildx build --platform linux/arm64 -f deploy/aws/Dockerfile.agent -t "$AGENT_REPO:$TAG" --push .

log "4. runtimes, gateway, IAM, observability"
cd deploy/aws/terraform
terraform apply ${APPROVE[@]+"${APPROVE[@]}"} -var "mcp_image_tag=$TAG" -var "agent_image_tag=$TAG"

log "5. endpoints"
terraform output
cat <<EOF

Smoke test (bills; model calls on Bedrock):
  I_ACCEPT_CLOUD_COSTS=yes uv run python deploy/smoke_test.py \\
    --agent-url "\$(terraform -chdir=deploy/aws/terraform output -raw agent_invoke_url)" --agent-auth sigv4
Tear down with: I_ACCEPT_CLOUD_COSTS=yes make destroy-aws
EOF
