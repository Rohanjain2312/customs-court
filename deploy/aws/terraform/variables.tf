variable "i_accept_cloud_costs" {
  description = "Must be \"yes\". A second guard next to deploy.sh: plan and apply fail without it."
  type        = string

  validation {
    condition     = var.i_accept_cloud_costs == "yes"
    error_message = "Refusing: these resources bill. Set i_accept_cloud_costs = \"yes\" only if you intend to pay."
  }
}

variable "region" {
  description = "AWS Region with AgentCore Runtime, Gateway and Claude on Bedrock."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for resource names. AgentCore runtime names allow letters, digits and underscores."
  type        = string
  default     = "tariffagent"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,30}$", var.name_prefix))
    error_message = "name_prefix must start with a letter and use only letters, digits and underscores."
  }
}

variable "mcp_image_tag" {
  description = "Tag of the MCP server image pushed to the mcp ECR repository (deploy.sh sets it)."
  type        = string
  default     = "unset"
}

variable "agent_image_tag" {
  description = "Tag of the agent image pushed to the agent ECR repository (deploy.sh sets it)."
  type        = string
  default     = "unset"
}

variable "reasoner_model" {
  description = "Model name the agent uses. tariffagent.llm.cloud maps it to the Bedrock model id."
  type        = string
  default     = "claude-sonnet-5"
}

variable "bedrock_model_ids" {
  description = "Bedrock model ids the agent role may invoke (bedrock-runtime and bedrock-mantle)."
  type        = list(string)
  default     = ["anthropic.claude-sonnet-5", "anthropic.claude-haiku-4-5"]
}

variable "agent_inbound_auth" {
  description = "Inbound auth for the agent runtime: IAM (SigV4, default) or JWT (bring your own OIDC provider)."
  type        = string
  default     = "IAM"

  validation {
    condition     = contains(["IAM", "JWT"], var.agent_inbound_auth)
    error_message = "agent_inbound_auth must be IAM or JWT."
  }
}

variable "jwt_discovery_url" {
  description = "OIDC discovery URL (ends with /.well-known/openid-configuration). Used when agent_inbound_auth = JWT."
  type        = string
  default     = ""
}

variable "jwt_allowed_clients" {
  description = "Allowed client_id values for JWT inbound auth."
  type        = list(string)
  default     = []
}

variable "jwt_allowed_audience" {
  description = "Allowed aud values for JWT inbound auth."
  type        = list(string)
  default     = []
}

variable "invoker_principal_arns" {
  description = "IAM principals (for example a backend role) allowed to invoke the agent runtime when agent_inbound_auth = IAM."
  type        = list(string)
  default     = []
}

variable "agent_max_turns" {
  description = "Hard cap on model turns per classification."
  type        = number
  default     = 10
}

variable "agent_token_budget" {
  description = "Hard cap on input plus output tokens per classification."
  type        = number
  default     = 120000
}

variable "idle_session_timeout_seconds" {
  description = "AgentCore idle session timeout. Short keeps idle memory billing low."
  type        = number
  default     = 120
}

variable "max_session_lifetime_seconds" {
  description = "AgentCore maximum session lifetime."
  type        = number
  default     = 900
}

variable "log_retention_days" {
  description = "Retention for log groups created here."
  type        = number
  default     = 30
}

variable "enable_transaction_search" {
  description = "Account-wide, one-time CloudWatch Transaction Search setup (X-Ray segments to CloudWatch Logs). Needed for AgentCore spans. Leave false if the account already has it."
  type        = bool
  default     = false
}
