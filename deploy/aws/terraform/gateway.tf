# AgentCore Gateway in front of the MCP runtime.
# Inbound: AWS_IAM (callers need bedrock-agentcore:InvokeGateway; the agent role has it).
# Outbound: the gateway signs requests to the MCP runtime with its own role
# (GATEWAY_IAM_ROLE, service bedrock-agentcore), per gateway-target-MCPservers.html.
# Tool names through the gateway are "tariffagent-mcp___<tool>" (gateway-tool-naming.html).

resource "aws_bedrockagentcore_gateway" "mcp" {
  name            = local.gateway_name
  description     = "TariffAgent tools (MCP) for the TariffAgent agent"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"
}

resource "aws_bedrockagentcore_gateway_target" "mcp_runtime" {
  name               = local.gateway_target
  gateway_identifier = aws_bedrockagentcore_gateway.mcp.gateway_id
  description        = "TariffAgent MCP server on AgentCore Runtime"

  credential_provider_configuration {
    gateway_iam_role {
      service = "bedrock-agentcore"
    }
  }

  target_configuration {
    mcp {
      mcp_server {
        endpoint = local.mcp_runtime_invoke_url
      }
    }
  }

  # Reuse the runtime session (microVM affinity) across tool calls. Applies to
  # MCP 2025-11-25 and earlier (gateway-target-MCPservers.html, tip).
  metadata_configuration {
    allowed_request_headers  = ["Mcp-Session-Id"]
    allowed_response_headers = ["Mcp-Session-Id"]
  }

  # The target syncs tools/list on create, so the MCP runtime and its policy must exist.
  depends_on = [
    aws_bedrockagentcore_resource_policy.mcp_runtime,
    aws_iam_role_policy.gateway,
  ]
}
