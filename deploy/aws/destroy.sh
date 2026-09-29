#!/usr/bin/env bash
# Destroy the TariffAgent AgentCore deployment. Deploy-ready, never run by the project.
#
# Prints the cost estimate of what is running, then refuses unless I_ACCEPT_CLOUD_COSTS=yes
# (the same explicit opt-in as deploy.sh, so no cloud command runs by accident).
# `make destroy-aws` calls it. terraform destroy removes the runtimes, gateway, IAM,
# log deliveries and both ECR repositories with their images (force_delete).
# Terraform asks for approval unless AUTO_APPROVE=yes.
# Not removed: the account-wide Transaction Search setting if you enabled it outside
# this state, and the log groups AgentCore created for the runtimes
# (/aws/bedrock-agentcore/runtimes/*); delete those by hand if you want them gone.
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
cd "$REPO_ROOT"

print_cost_estimate aws
require_cost_opt_in

need aws
need terraform
APPROVE=()
[ "${AUTO_APPROVE:-}" = "yes" ] && APPROVE=(-auto-approve)
export TF_VAR_i_accept_cloud_costs=yes TF_VAR_region="${AWS_REGION:-us-east-1}"

log "AWS identity"
aws sts get-caller-identity --output text

cd deploy/aws/terraform
terraform init -input=false
terraform destroy ${APPROVE[@]+"${APPROVE[@]}"}
log "destroyed. Check the console for leftover runtime log groups."
