# TariffAgent on Amazon Bedrock AgentCore. Deploy-ready, not deployed.
# Validated locally with `terraform init -backend=false && terraform validate` only.
# Never run plan or apply without reading deploy/aws/deploy.sh and the cost estimate.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # aws_bedrockagentcore_* resources used here were checked against provider 6.66.0.
      version = ">= 6.66.0, < 7.0.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = "customs-court"
      app     = "tariffagent"
    }
  }
}
