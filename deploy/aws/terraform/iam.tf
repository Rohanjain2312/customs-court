# IAM for the two runtimes and the gateway. Least privilege, following
# runtime-permissions.html (execution role and trust policy, checked 2026-09-28).

# Trust: only AgentCore in this account and region may assume the roles
# (confused deputy protection with aws:SourceAccount and aws:SourceArn).
data "aws_iam_policy_document" "agentcore_trust" {
  statement {
    sid     = "AssumeRolePolicy"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:*"]
    }
  }
}

# Statements every runtime needs: pull its image, write logs, traces and metrics.
data "aws_iam_policy_document" "runtime_base" {
  statement {
    sid       = "ECRToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "LogGroups"
    actions   = ["logs:DescribeLogStreams", "logs:CreateLogGroup"]
    resources = ["${local.runtime_log_group_prefix}/*"]
  }
  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:*"]
  }
  statement {
    sid       = "LogEvents"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.runtime_log_group_prefix}/*:log-stream:*"]
  }
  statement {
    sid       = "Traces"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }
  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
}

# ---- MCP server runtime -------------------------------------------------------

resource "aws_iam_role" "mcp_runtime" {
  name               = "${var.name_prefix}-mcp-runtime"
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
}

data "aws_iam_policy_document" "mcp_runtime" {
  source_policy_documents = [data.aws_iam_policy_document.runtime_base.json]
  statement {
    sid       = "PullMcpImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.mcp.arn]
  }
  statement {
    sid       = "SpanDestination"
    actions   = ["logs:PutResourcePolicy"]
    resources = ["${local.runtime_log_group_prefix}/${local.mcp_runtime_name}-*"]
  }
}

resource "aws_iam_role_policy" "mcp_runtime" {
  name   = "runtime"
  role   = aws_iam_role.mcp_runtime.id
  policy = data.aws_iam_policy_document.mcp_runtime.json
}

# ---- Agent runtime ------------------------------------------------------------

resource "aws_iam_role" "agent_runtime" {
  name               = "${var.name_prefix}-agent-runtime"
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
}

data "aws_iam_policy_document" "agent_runtime" {
  source_policy_documents = [data.aws_iam_policy_document.runtime_base.json]
  statement {
    sid       = "PullAgentImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.agent.arn]
  }
  statement {
    sid       = "SpanDestination"
    actions   = ["logs:PutResourcePolicy"]
    resources = ["${local.runtime_log_group_prefix}/${local.agent_runtime_name}-*"]
  }
  # Claude through bedrock-runtime (InvokeModel, inference profiles).
  statement {
    sid     = "InvokeClaude"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = flatten([
      for id in var.bedrock_model_ids : [
        "arn:${local.partition}:bedrock:*::foundation-model/${id}*",
        "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:inference-profile/*${id}*",
      ]
    ])
  }
  # The adapter uses the Anthropic SDK's Bedrock Mantle client. Mantle has its own
  # IAM namespace; bedrock:* actions do not cover it (inference-messages-api.html).
  statement {
    sid       = "InvokeClaudeMantle"
    actions   = ["bedrock-mantle:CreateInference"]
    resources = ["arn:${local.partition}:bedrock-mantle:${local.region}:${local.account_id}:project/*"]
  }
  statement {
    sid       = "CallGateway"
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [aws_bedrockagentcore_gateway.mcp.gateway_arn]
  }
}

resource "aws_iam_role_policy" "agent_runtime" {
  name   = "runtime"
  role   = aws_iam_role.agent_runtime.id
  policy = data.aws_iam_policy_document.agent_runtime.json
}

# ---- Gateway ------------------------------------------------------------------

data "aws_iam_policy_document" "gateway_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:gateway/*"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${var.name_prefix}-gateway"
  assume_role_policy = data.aws_iam_policy_document.gateway_trust.json
}

data "aws_iam_policy_document" "gateway" {
  statement {
    sid     = "InvokeMcpRuntime"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn,
      "${aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "invoke-mcp-runtime"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway.json
}
