output "mcp_ecr_repository_url" {
  value = aws_ecr_repository.mcp.repository_url
}

output "agent_ecr_repository_url" {
  value = aws_ecr_repository.agent.repository_url
}

output "mcp_runtime_arn" {
  value = aws_bedrockagentcore_agent_runtime.mcp.agent_runtime_arn
}

output "agent_runtime_arn" {
  value = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
}

output "gateway_url" {
  description = "MCP endpoint (SigV4, service bedrock-agentcore). Tool names carry the prefix below."
  value       = aws_bedrockagentcore_gateway.mcp.gateway_url
}

output "gateway_tool_prefix" {
  value = local.mcp_tool_prefix
}

output "agent_invoke_url" {
  description = "HTTPS InvokeAgentRuntime URL for deploy/smoke_test.py (SigV4 or JWT, per agent_inbound_auth)."
  value       = "https://bedrock-agentcore.${local.region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn)}/invocations?qualifier=DEFAULT"
}
