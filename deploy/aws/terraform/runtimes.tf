# Two AgentCore runtimes: the MCP server and the agent.

# ---- MCP server (MCP protocol, :8000 /mcp, stateless streamable HTTP) ---------
# Inbound auth: IAM (SigV4). This is the default when no authorizer_configuration
# is given (runtime-oauth.html). Only the gateway role may invoke it (policy below).
resource "aws_bedrockagentcore_agent_runtime" "mcp" {
  agent_runtime_name = local.mcp_runtime_name
  description        = "TariffAgent MCP server (read-only HTS and CROSS tools)"
  role_arn           = aws_iam_role.mcp_runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = local.mcp_image
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "MCP"
  }

  lifecycle_configuration {
    idle_runtime_session_timeout = var.idle_session_timeout_seconds
    max_lifetime                 = var.max_session_lifetime_seconds
  }

  environment_variables = {
    # Hide evaluation-set rulings so the endpoint cannot leak golden answers.
    REDACT_EVAL = "true"
  }

  depends_on = [aws_iam_role_policy.mcp_runtime]
}

# Only the gateway role may invoke the MCP runtime. The explicit deny keys on
# aws:PrincipalArn, so a broad identity policy elsewhere cannot bypass the gateway
# (runtime-oauth.html, "Restrict IAM (SigV4) inbound invocation to your gateway").
data "aws_iam_policy_document" "mcp_runtime_resource" {
  statement {
    sid     = "AllowOnlyGatewayRole"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.gateway.arn]
    }
    resources = [aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn]
  }
  statement {
    sid     = "DenyOtherPrincipals"
    effect  = "Deny"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    resources = [aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn]
    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = [aws_iam_role.gateway.arn]
    }
  }
}

resource "aws_bedrockagentcore_resource_policy" "mcp_runtime" {
  resource_arn = aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn
  policy       = data.aws_iam_policy_document.mcp_runtime_resource.json
}

# ---- Agent (HTTP protocol, :8080 /invocations and /ping) ----------------------
# Inbound auth: IAM by default; JWT when agent_inbound_auth = "JWT". A runtime
# accepts one of the two, not both (runtime-oauth.html).
resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = local.agent_runtime_name
  description        = "TariffAgent single agent (Claude on Bedrock, tools through the gateway)"
  role_arn           = aws_iam_role.agent_runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = local.agent_image
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  lifecycle_configuration {
    idle_runtime_session_timeout = var.idle_session_timeout_seconds
    max_lifetime                 = var.max_session_lifetime_seconds
  }

  dynamic "authorizer_configuration" {
    for_each = var.agent_inbound_auth == "JWT" ? [1] : []
    content {
      custom_jwt_authorizer {
        discovery_url    = var.jwt_discovery_url
        allowed_clients  = var.jwt_allowed_clients
        allowed_audience = var.jwt_allowed_audience
      }
    }
  }

  environment_variables = {
    AGENT_MODEL_MODE            = "bedrock"
    AGENT_OBSERVABILITY_ENABLED = "true"
    AGENT_MAX_TURNS             = tostring(var.agent_max_turns)
    AGENT_TOKEN_BUDGET          = tostring(var.agent_token_budget)
    REASONER_MODEL              = var.reasoner_model
    MCP_URL                     = aws_bedrockagentcore_gateway.mcp.gateway_url
    MCP_AUTH                    = "sigv4"
    MCP_TOOL_PREFIX             = local.mcp_tool_prefix
    # tariffagent.llm.cloud refuses to build a real Bedrock client without this.
    # It only reaches the container because var.i_accept_cloud_costs is "yes".
    I_ACCEPT_CLOUD_COSTS = var.i_accept_cloud_costs
  }

  depends_on = [aws_iam_role_policy.agent_runtime]
}

# Optional: extra IAM principals (for example a backend role) that may invoke the agent.
data "aws_iam_policy_document" "agent_runtime_resource" {
  count = var.agent_inbound_auth == "IAM" && length(var.invoker_principal_arns) > 0 ? 1 : 0
  statement {
    sid     = "AllowInvokers"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    principals {
      type        = "AWS"
      identifiers = var.invoker_principal_arns
    }
    resources = [aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn]
  }
  # The agent never needs per-user OAuth delegation; deny the user-id header path.
  statement {
    sid     = "DenyUserIdDelegation"
    effect  = "Deny"
    actions = ["bedrock-agentcore:InvokeAgentRuntimeForUser"]
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    resources = [aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn]
  }
}

resource "aws_bedrockagentcore_resource_policy" "agent_runtime" {
  count        = length(data.aws_iam_policy_document.agent_runtime_resource)
  resource_arn = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
  policy       = data.aws_iam_policy_document.agent_runtime_resource[0].json
}
