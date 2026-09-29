"""Create or delete the TariffAgent ADK agent on Vertex AI Agent Runtime.

Deploy-ready, not deployed. Never run by the build or the tests. deploy.sh and
destroy.sh call it with deploy/gcp/.venv/bin/python after their cost guard.

    python deploy_agent_runtime.py create --project P --location us-central1 \
        --staging-bucket gs://B --service-account SA --mcp-url https://.../mcp
    python deploy_agent_runtime.py delete --resource projects/P/locations/L/reasoningEngines/ID

API checked against google-cloud-aiplatform 2.2.0 on 2026-09-28:
vertexai.Client(project, location).agent_engines.create(agent=AdkApp(...), config={...}),
where config fields include requirements, extra_packages, staging_bucket, env_vars,
service_account, display_name, min_instances, max_instances and resource_limits.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def guard() -> None:
    if os.environ.get("I_ACCEPT_CLOUD_COSTS") != "yes":
        print(
            "REFUSING: Agent Runtime bills. Set I_ACCEPT_CLOUD_COSTS=yes to proceed on purpose.",
            file=sys.stderr,
        )
        sys.exit(3)


def requirements() -> list[str]:
    lines = (HERE / "requirements.txt").read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def create(a) -> None:
    import vertexai
    from vertexai.agent_engines import AdkApp

    sys.path.insert(0, str(HERE))
    os.environ["GOOGLE_CLOUD_PROJECT_ID"] = a.project
    os.environ["MCP_URL"] = a.mcp_url
    from tariff_adk.agent import build_app

    vertexai.init(project=a.project, location=a.location, staging_bucket=a.staging_bucket)
    client = vertexai.Client(project=a.project, location=a.location)
    app = AdkApp(app=build_app())
    remote = client.agent_engines.create(
        agent=app,
        config={
            "display_name": "tariffagent",
            "description": "TariffAgent HTS classifier (ADK, Claude on Vertex AI, MCP tools on Cloud Run)",
            "requirements": requirements(),
            "extra_packages": [str(HERE / "tariff_adk")],
            "staging_bucket": a.staging_bucket,
            "service_account": a.service_account,
            "env_vars": {
                "MCP_URL": a.mcp_url,
                "MCP_AUTH": "google-id-token",
                "GOOGLE_CLOUD_PROJECT_ID": a.project,
                "CLAUDE_VERTEX_REGION": a.claude_region,
            },
            # Expected to scale to zero between requests (not verified on a live deploy).
            "min_instances": 0,
            "max_instances": 2,
            "resource_limits": {"cpu": "1", "memory": "2Gi"},
        },
    )
    print(f"created: {remote.api_resource.name}")


def delete(a) -> None:
    import vertexai

    parts = a.resource.split("/")
    client = vertexai.Client(project=parts[1], location=parts[3])
    client.agent_engines.delete(name=a.resource, force=True)
    print(f"deleted: {a.resource}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--project", required=True)
    c.add_argument("--location", default="us-central1")
    c.add_argument("--staging-bucket", required=True)
    c.add_argument("--service-account", required=True)
    c.add_argument("--mcp-url", required=True)
    c.add_argument("--claude-region", default="global")
    d = sub.add_parser("delete")
    d.add_argument("--resource", required=True)
    a = ap.parse_args()
    guard()
    create(a) if a.cmd == "create" else delete(a)


if __name__ == "__main__":
    main()
