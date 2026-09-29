"""Print an estimated monthly cost for the AWS or GCP deployment. Deploy-ready, not deployed.

    python3 deploy/cost_estimate.py aws|gcp [--classifications N]

Standard library only, so deploy.sh can call it before anything else. Every number is
an estimate ("expected, not measured"): nothing has been deployed. Prices were read
from the pricing pages listed with each price on the date in CHECKED.
"""

from __future__ import annotations

import argparse
import os

CHECKED = "2026-09-28"

# ---- Workload assumptions (edit to taste) --------------------------------------
# Model cost per classification: dev pilot average on the Anthropic API with prompt
# caching (docs/PROGRESS.md, Phase 3: $0.036 per item). Claude list prices on Bedrock
# and Vertex were not checked separately; they are assumed equal to Anthropic's.
MODEL_USD_PER_CLASSIFICATION = 0.036
TOOL_CALLS_PER_CLASSIFICATION = 6  # pilot runs made about 4 to 8 tool calls
AGENT_ACTIVE_CPU_S = 3.0  # CPU busy time per classification; the rest is waiting on the model
SESSION_S = 30.0  # wall time of one classification (pilot p50 about 11 s of API time)
MCP_ACTIVE_CPU_S = 2.0  # SQLite and BM25 work for all tool calls of one classification
# Registry storage is billed on compressed layers. Real-data arm64 MCP image with
# vectors, measured locally 2026-09-28: 0.73 GB compressed, 3.33 GB unpacked.
MCP_IMAGE_GB = 0.73
AGENT_IMAGE_GB = 0.12  # agent image, compressed layers, measured locally (536 MB unpacked)
LOG_GB = 0.5

AWS_PRICES = {
    # https://aws.amazon.com/bedrock/agentcore/pricing/ (Runtime v2 consumption rates)
    "runtime_vcpu_hour": 0.1276,
    "runtime_gb_hour": 0.0169,
    "gateway_per_1000_invocations": 0.005,
    "gateway_per_100_tools_indexed_month": 0.02,
    "identity": 0.0,  # "no additional charge" when used through Runtime or Gateway
    # https://aws.amazon.com/ecr/pricing/
    "ecr_gb_month": 0.10,
    # https://aws.amazon.com/cloudwatch/pricing/ (first 5 GB of logs free, spans $0.35/GB)
    "logs_gb_after_free": 0.50,
    "logs_free_gb": 5.0,
    "spans_gb": 0.35,
}
AWS_SOURCES = [
    "https://aws.amazon.com/bedrock/agentcore/pricing/",
    "https://aws.amazon.com/ecr/pricing/",
    "https://aws.amazon.com/cloudwatch/pricing/",
]

GCP_PRICES = {
    # https://cloud.google.com/run/pricing (request-based billing, us-central1)
    "run_vcpu_s": 0.000024,
    "run_gib_s": 0.0000025,
    "run_per_million_requests": 0.40,
    "run_free_vcpu_s": 180_000,
    "run_free_gib_s": 360_000,
    "run_free_requests": 2_000_000,
    # https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing
    # Agent Runtime: Agent Compute $0.085/vCPU-h, Agent Memory $0.009/GiB-h. Sessions
    # storage $0.30/GiB-month (billing from 2026-09-01). The page lists no free tier.
    "agent_vcpu_hour": 0.085,
    "agent_gib_hour": 0.009,
    "agent_storage_gib_month": 0.30,
    # https://cloud.google.com/artifact-registry/pricing (first 0.5 GiB free)
    "registry_gib_month": 0.10,
    "registry_free_gib": 0.5,
    # https://cloud.google.com/stackdriver/pricing (first 50 GiB of logs free per project)
    "logging_gib_after_free": 0.50,
    "logging_free_gib": 50.0,
}
GCP_SOURCES = [
    "https://cloud.google.com/run/pricing",
    "https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing",
    "https://cloud.google.com/artifact-registry/pricing",
    "https://cloud.google.com/stackdriver/pricing",
]


def aws(n: int) -> list[tuple[str, float, str]]:
    p = AWS_PRICES
    idle = 120.0  # idle_session_timeout_seconds in terraform/variables.tf
    agent_cpu = n * AGENT_ACTIVE_CPU_S / 3600 * 1.0 * p["runtime_vcpu_hour"]
    agent_mem = n * (SESSION_S + idle) / 3600 * 1.0 * p["runtime_gb_hour"]
    mcp_cpu = n * MCP_ACTIVE_CPU_S / 3600 * 1.0 * p["runtime_vcpu_hour"]
    mcp_mem = n * (SESSION_S + idle) / 3600 * 2.0 * p["runtime_gb_hour"]
    gw = n * TOOL_CALLS_PER_CLASSIFICATION / 1000 * p["gateway_per_1000_invocations"]
    indexing = 8 / 100 * p["gateway_per_100_tools_indexed_month"]
    ecr = (MCP_IMAGE_GB + AGENT_IMAGE_GB) * p["ecr_gb_month"]
    scale = n / 1000  # logs and spans grow with traffic: 0.5 GB and 0.1 GB per 1,000 runs
    logs = (
        max(0.0, LOG_GB * scale - p["logs_free_gb"]) * p["logs_gb_after_free"] + 0.1 * scale * p["spans_gb"]
    )
    model = n * MODEL_USD_PER_CLASSIFICATION
    return [
        ("AgentCore Runtime, agent (3 s CPU, 1 GB for 150 s)", agent_cpu + agent_mem, "per use"),
        ("AgentCore Runtime, MCP server (2 s CPU, 2 GB for 150 s)", mcp_cpu + mcp_mem, "per use"),
        ("AgentCore Gateway tool calls", gw, "per use"),
        ("AgentCore Gateway tool indexing (8 tools)", indexing, "fixed"),
        ("AgentCore Identity (free through Runtime and Gateway)", 0.0, "per use"),
        ("ECR storage (both images)", ecr, "fixed"),
        ("CloudWatch logs and spans (0.5 + 0.1 GB per 1,000)", logs, "per use"),
        ("Claude on Bedrock (tokens, assumed = Anthropic list price)", model, "per use"),
    ]


def gcp(n: int) -> list[tuple[str, float, str]]:
    p = GCP_PRICES
    reqs = n * TOOL_CALLS_PER_CLASSIFICATION
    vcpu_s = reqs * 0.5 * 1.0  # about 0.5 s per MCP request, 1 vCPU, request-based billing
    gib_s = reqs * 0.5 * 2.0
    run = (
        max(0.0, vcpu_s - p["run_free_vcpu_s"]) * p["run_vcpu_s"]
        + max(0.0, gib_s - p["run_free_gib_s"]) * p["run_gib_s"]
        + max(0.0, reqs - p["run_free_requests"]) / 1e6 * p["run_per_million_requests"]
    )
    agent = n * SESSION_S / 3600 * (1.0 * p["agent_vcpu_hour"] + 2.0 * p["agent_gib_hour"])
    # About 10 kB of session events per classification, 20 writes each.
    sessions = n * 1e-5 * p["agent_storage_gib_month"] + n * 20 / 1e6 * p["agent_vcpu_hour"]
    registry = max(0.0, MCP_IMAGE_GB - p["registry_free_gib"]) * p["registry_gib_month"]
    logs = max(0.0, LOG_GB * n / 1000 - p["logging_free_gib"]) * p["logging_gib_after_free"]
    model = n * MODEL_USD_PER_CLASSIFICATION
    return [
        ("Cloud Run MCP server (request-based, inside free tier)", run, "per use"),
        ("Agent Runtime (1 vCPU, 2 GiB, 30 s each, min_instances=0)", agent, "per use"),
        ("Agent Runtime Sessions (storage + writes)", sessions, "per use"),
        ("Artifact Registry storage (MCP image)", registry, "fixed"),
        ("Cloud Logging (inside the 50 GiB free allotment)", logs, "per use"),
        ("Claude on Vertex AI (tokens, assumed = Anthropic list price)", model, "per use"),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cloud", choices=["aws", "gcp"])
    ap.add_argument(
        "--classifications",
        type=int,
        default=int(os.environ.get("CLASSIFICATIONS_PER_MONTH", "1000")),
        help="classifications per month (default 1000, or CLASSIFICATIONS_PER_MONTH)",
    )
    a = ap.parse_args(argv)
    rows = aws(a.classifications) if a.cloud == "aws" else gcp(a.classifications)
    sources = AWS_SOURCES if a.cloud == "aws" else GCP_SOURCES
    total = sum(r[1] for r in rows)
    fixed = sum(r[1] for r in rows if r[2] == "fixed")
    print(f"Estimated monthly cost, {a.cloud.upper()}, {a.classifications} classifications/month")
    print(f"Expected, not measured. Prices checked {CHECKED}. Nothing has been deployed.")
    print("-" * 78)
    for name, usd, _ in rows:
        print(f"  {name:66s} ${usd:8.2f}")
    print("-" * 78)
    print(f"  {'Total':66s} ${total:8.2f}")
    print(f"  {'Of which fixed (paid even with zero traffic)':66s} ${fixed:8.2f}")
    print("Sources:")
    for s in sources:
        print(f"  {s}")
    print("Assumptions: deploy/cost_estimate.py (top of file). Taxes and data transfer not included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
