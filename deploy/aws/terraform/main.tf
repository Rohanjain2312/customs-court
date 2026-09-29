# Architecture (deploy-ready, not deployed):
#
#   caller --(SigV4 or JWT)--> agent runtime (HTTP, :8080 /invocations)
#     agent --(Bedrock Messages API, IAM role)--> Claude on Bedrock
#     agent --(MCP over HTTPS, SigV4)--> AgentCore Gateway (AWS_IAM inbound)
#       gateway --(SigV4 with the gateway role)--> MCP runtime (MCP, :8000 /mcp)
#
# The MCP runtime accepts calls only from the gateway role (resource policy with an
# explicit deny for every other principal). The agent never sees AWS keys; it uses
# its execution role. Spans and logs go to CloudWatch (observability.tf).

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = var.region

  mcp_runtime_name   = "${var.name_prefix}_mcp"
  agent_runtime_name = "${var.name_prefix}_agent"
  gateway_name       = replace("${var.name_prefix}-gateway", "_", "-")
  gateway_target     = "tariffagent-mcp"

  # Gateway tool names are "<target name>___<tool name>" (gateway-tool-naming.html).
  mcp_tool_prefix = "${local.gateway_target}___"

  mcp_image   = "${aws_ecr_repository.mcp.repository_url}:${var.mcp_image_tag}"
  agent_image = "${aws_ecr_repository.agent.repository_url}:${var.agent_image_tag}"

  # InvokeAgentRuntime over HTTPS for an MCP runtime (runtime-mcp.html, step 4).
  mcp_runtime_invoke_url = "https://bedrock-agentcore.${local.region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn)}/invocations?qualifier=DEFAULT"

  runtime_log_group_prefix = "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes"
}
