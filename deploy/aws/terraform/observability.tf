# AgentCore Observability (observability-configure.html, checked 2026-09-28).
#
# - Runtimes: AgentCore creates /aws/bedrock-agentcore/runtimes/<id>-<endpoint> log
#   groups itself. The agent image runs under ADOT (aws-opentelemetry-distro) when
#   AGENT_OBSERVABILITY_ENABLED=true, so spans reach CloudWatch.
# - Gateway: no logs by default. Vended log delivery below sends APPLICATION_LOGS to a
#   log group and TRACES to X-Ray.
# - Spans need CloudWatch Transaction Search, an account-wide one-time setting. It is
#   opt-in here (enable_transaction_search) because it changes the account.

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/aws/vendedlogs/bedrock-agentcore/gateway/APPLICATION_LOGS/${aws_bedrockagentcore_gateway.mcp.gateway_id}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_delivery_source" "gateway_logs" {
  name         = "${var.name_prefix}-gateway-logs"
  log_type     = "APPLICATION_LOGS"
  resource_arn = aws_bedrockagentcore_gateway.mcp.gateway_arn
}

resource "aws_cloudwatch_log_delivery_destination" "gateway_logs" {
  name = "${var.name_prefix}-gateway-logs"
  delivery_destination_configuration {
    destination_resource_arn = aws_cloudwatch_log_group.gateway.arn
  }
}

resource "aws_cloudwatch_log_delivery" "gateway_logs" {
  delivery_source_name     = aws_cloudwatch_log_delivery_source.gateway_logs.name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.gateway_logs.arn
}

resource "aws_cloudwatch_log_delivery_source" "gateway_traces" {
  name         = "${var.name_prefix}-gateway-traces"
  log_type     = "TRACES"
  resource_arn = aws_bedrockagentcore_gateway.mcp.gateway_arn
}

resource "aws_cloudwatch_log_delivery_destination" "gateway_traces" {
  name                      = "${var.name_prefix}-gateway-traces"
  delivery_destination_type = "XRAY"
}

resource "aws_cloudwatch_log_delivery" "gateway_traces" {
  delivery_source_name     = aws_cloudwatch_log_delivery_source.gateway_traces.name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.gateway_traces.arn
}

# ---- Transaction Search (account-wide, opt-in) --------------------------------

data "aws_iam_policy_document" "xray_to_logs" {
  count = var.enable_transaction_search ? 1 : 0
  statement {
    sid     = "TransactionSearchXRayAccess"
    effect  = "Allow"
    actions = ["logs:PutLogEvents"]
    principals {
      type        = "Service"
      identifiers = ["xray.amazonaws.com"]
    }
    resources = [
      "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:aws/spans:*",
      "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/application-signals/data:*",
    ]
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:xray:${local.region}:${local.account_id}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "xray_to_logs" {
  count           = var.enable_transaction_search ? 1 : 0
  policy_name     = "${var.name_prefix}-transaction-search"
  policy_document = data.aws_iam_policy_document.xray_to_logs[0].json
}

resource "aws_xray_trace_segment_destination" "cloudwatch" {
  count       = var.enable_transaction_search ? 1 : 0
  destination = "CloudWatchLogs"
  depends_on  = [aws_cloudwatch_log_resource_policy.xray_to_logs]
}
