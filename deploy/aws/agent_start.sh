#!/bin/sh
# Start the AgentCore agent. Deploy-ready, not deployed.
# In AgentCore Runtime, set AGENT_OBSERVABILITY_ENABLED=true (Terraform does) so the
# process runs under ADOT auto-instrumentation and spans reach CloudWatch.
# Locally it runs plain uvicorn, so no telemetry exporter tries to reach AWS.
set -eu
if [ "${AGENT_OBSERVABILITY_ENABLED:-false}" = "true" ]; then
  exec opentelemetry-instrument uvicorn agentcore_agent.app:app --host 0.0.0.0 --port 8080 --no-access-log
fi
exec uvicorn agentcore_agent.app:app --host 0.0.0.0 --port 8080 --no-access-log
