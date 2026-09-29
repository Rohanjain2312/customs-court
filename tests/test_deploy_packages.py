"""Offline checks of the deploy-ready AWS and GCP packages (deploy/).

Fast, no docker, no network, no cloud account, no model API. The container builds and
the MCP client calls against running containers live in deploy/*/build_and_validate.sh.
Tests that need an optional tool (terraform, the isolated ADK venv) skip without it.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
AWS = DEPLOY / "aws"
GCP = DEPLOY / "gcp"
TF = AWS / "terraform"
ADK_PY = GCP / ".venv" / "bin" / "python"
HANDBAG = (
    "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, two shoulder straps."
)


def _env_without_opt_in() -> dict:
    env = dict(os.environ)
    env.pop("I_ACCEPT_CLOUD_COSTS", None)
    return env


# ---- Guard scripts ----------------------------------------------------------------


@pytest.mark.parametrize("script", ["aws/deploy.sh", "aws/destroy.sh", "gcp/deploy.sh", "gcp/destroy.sh"])
def test_guard_scripts_refuse_without_opt_in(script):
    if not shutil.which("bash"):
        pytest.skip("bash not available")
    r = subprocess.run(
        ["bash", str(DEPLOY / script)], env=_env_without_opt_in(), capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 3, (r.returncode, r.stdout[-500:], r.stderr[-500:])
    # The estimate comes first, then the refusal, and nothing else ran.
    assert "Estimated monthly cost" in r.stdout
    assert "expected, not measured" in r.stdout.lower()
    assert "REFUSING" in r.stderr
    assert "==>" not in r.stdout  # no step of the script started


def test_guard_scripts_check_opt_in_before_any_cloud_command():
    for script in ["aws/deploy.sh", "aws/destroy.sh", "gcp/deploy.sh", "gcp/destroy.sh"]:
        text = (DEPLOY / script).read_text()
        guard_at = text.index("require_cost_opt_in")
        estimate_at = text.index("print_cost_estimate")
        assert estimate_at < guard_at
        for cmd in ("aws ", "terraform ", "gcloud ", "docker "):
            first = [m.start() for m in re.finditer(rf"^\s*{cmd}", text, re.M)]
            assert all(i > guard_at for i in first), (script, cmd)


def test_agent_runtime_deployer_refuses_without_opt_in():
    r = subprocess.run(
        [
            sys.executable,
            str(GCP / "deploy_agent_runtime.py"),
            "delete",
            "--resource",
            "projects/p/locations/l/x/y",
        ],
        env=_env_without_opt_in(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 3 and "REFUSING" in r.stderr


def test_terraform_requires_explicit_cost_variable():
    text = (TF / "variables.tf").read_text()
    block = text[text.index('variable "i_accept_cloud_costs"') :]
    assert "default" not in block.split("}\n}")[0], "the cost variable must have no default"
    assert 'var.i_accept_cloud_costs == "yes"' in block


# ---- Cost estimate ------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_cost_estimate_cites_pricing_pages(cloud, capsys):
    sys.path.insert(0, str(DEPLOY))
    import cost_estimate

    assert cost_estimate.main([cloud, "--classifications", "1000"]) == 0
    out = capsys.readouterr().out
    assert "Expected, not measured" in out and cost_estimate.CHECKED in out
    assert re.search(r"Total\s+\$\s*\d+\.\d\d", out)
    assert out.count("https://") >= 3


def test_cost_estimate_is_zero_model_cost_without_traffic(capsys):
    sys.path.insert(0, str(DEPLOY))
    import cost_estimate

    rows = cost_estimate.aws(0) + cost_estimate.gcp(0)
    per_use = sum(usd for _, usd, kind in rows if kind == "per use")
    assert per_use < 0.01


# ---- Terraform ----------------------------------------------------------------------

TF_RESOURCES = [
    "aws_ecr_repository",
    "aws_bedrockagentcore_agent_runtime",
    "aws_bedrockagentcore_gateway",
    "aws_bedrockagentcore_gateway_target",
    "aws_bedrockagentcore_resource_policy",
    "aws_iam_role",
    "aws_cloudwatch_log_delivery_source",
    "aws_xray_trace_segment_destination",
]


def test_terraform_files_exist_and_cover_the_design():
    files = {p.name for p in TF.glob("*.tf")}
    assert {"versions.tf", "variables.tf", "main.tf", "runtimes.tf", "gateway.tf", "iam.tf"} <= files
    text = "\n".join(p.read_text() for p in TF.glob("*.tf"))
    for r in TF_RESOURCES:
        assert f'resource "{r}"' in text, r
    assert 'server_protocol = "MCP"' in text and 'server_protocol = "HTTP"' in text
    assert 'authorizer_type = "AWS_IAM"' in text
    assert 'service = "bedrock-agentcore"' in text
    assert "bedrock-mantle:CreateInference" in text
    assert not re.search(r"\b\d{12}\b", text), "no hardcoded account ids"
    assert 'AGENT_MODEL_MODE            = "bedrock"' in text


def test_terraform_validate_if_available():
    if not shutil.which("terraform") or not (TF / ".terraform").is_dir():
        pytest.skip("terraform or an initialized deploy/aws/terraform/.terraform is missing")
    r = subprocess.run(
        ["terraform", "validate", "-no-color"], cwd=TF, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---- Dockerfiles and requirements --------------------------------------------------


def test_dockerfiles_follow_the_platform_contracts():
    mcp = (AWS / "Dockerfile").read_text()
    assert "EXPOSE 8000" in mcp and '"--port", "8000"' in mcp and '"0.0.0.0"' in mcp
    assert "stateless" in (ROOT / "src/tariffagent/mcp_server/server.py").read_text()
    agent = (AWS / "Dockerfile.agent").read_text()
    assert "EXPOSE 8080" in agent and "USER app" in agent
    assert "--port 8080" in (AWS / "agent_start.sh").read_text()
    gcp = (GCP / "Dockerfile").read_text()
    assert '--port "${PORT}"' in gcp and "USER app" in gcp
    for d in (
        AWS / "Dockerfile.dockerignore",
        AWS / "Dockerfile.agent.dockerignore",
        GCP / "Dockerfile.dockerignore",
    ):
        assert d.read_text().splitlines()[1] == "*", f"{d} must start by excluding everything"


def _lock_versions() -> dict[str, str]:
    text = (ROOT / "uv.lock").read_text()
    return dict(re.findall(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text))


@pytest.mark.parametrize("req", [AWS / "requirements.txt", GCP / "requirements.txt"])
def test_requirements_pin_the_locked_versions(req):
    lock = _lock_versions()
    for line in req.read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?==(\S+)$", line.strip())
        if m and m.group(1).lower() in lock:
            assert lock[m.group(1).lower()] == m.group(3), (
                f"{req.name}: {line} vs uv.lock {lock[m.group(1).lower()]}"
            )


# ---- Data staging ---------------------------------------------------------------------


def test_export_deploy_data_fixture(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import export_deploy_data

    assert export_deploy_data.main(["--fixture", "--out", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["fixture"] is True and manifest["rows"]["rulings"] > 0
    con = sqlite3.connect(tmp_path / "data" / "tariffagent.sqlite")
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"  # read-only containers need no -wal
    agent = sqlite3.connect(tmp_path / "agent_data" / "tariffagent.sqlite")
    assert agent.execute("SELECT COUNT(*) FROM notes WHERE scope='gri'").fetchone()[0] == 1
    assert (tmp_path / "data" / "index").is_dir()


# ---- AWS agent entrypoint (mocked Bedrock, in-process tools) ------------------------


@pytest.fixture
def agent_app(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("anthropic")
    monkeypatch.syspath_prepend(str(AWS))
    import agentcore_agent.app as app

    importlib.reload(app)
    monkeypatch.setenv("MCP_URL", "http://127.0.0.1:9/mcp")
    monkeypatch.setenv("MCP_AUTH", "none")
    yield app
    app._provider = None
    app._scripted = None


def test_agent_ping_and_input_validation(agent_app):
    from fastapi.testclient import TestClient

    c = TestClient(agent_app.app)
    assert c.get("/ping").json() == {"status": "Healthy"}
    assert c.post("/invocations", json={"description": "  "}).status_code == 400
    assert c.post("/invocations", json=["not", "an", "object"]).status_code == 400
    assert c.post("/invocations", json={"description": "x" * 5000}).status_code == 400


def test_agent_real_bedrock_mode_refuses_without_opt_in(agent_app, monkeypatch):
    from tariffagent.llm.cloud import CloudCostGuard

    monkeypatch.delenv("I_ACCEPT_CLOUD_COSTS", raising=False)
    monkeypatch.setenv("AGENT_MODEL_MODE", "bedrock")
    with pytest.raises(CloudCostGuard):
        agent_app.get_provider()


def test_agent_invocation_with_scripted_bedrock(agent_app, monkeypatch):
    """Full /invocations path: real BedrockProvider over a mock transport, fixture tools in-process."""
    from fastapi.testclient import TestClient

    from tariffagent.agents import tooling
    from tariffagent.mcp_server.tools.core import TariffTools

    class FakeMCP(tooling.InProcessBackend):
        def __init__(self, _transport):
            super().__init__(TariffTools(use_vectors=False, redact_eval=True))

        def close(self):
            pass

    monkeypatch.setattr(tooling, "MCPBackend", FakeMCP)
    monkeypatch.setenv("AGENT_MODEL_MODE", "scripted")
    r = TestClient(agent_app.app).post("/invocations", json={"description": HANDBAG, "item_id": "t1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert re.match(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$", d["classification"]["hts10"])
    assert {"hts_search", "cross_search", "ruling_status"} <= set(d["tools_used"])
    s = d["scripted_bedrock_requests"]
    assert s["model_ids"] == ["anthropic.claude-sonnet-5"]
    assert s["system_cache_breakpoint"] and s["structured_output"]
    assert all(h.startswith("bedrock-mantle.") for h in s["hosts"])


def test_gateway_tool_prefix(agent_app):
    class Inner:
        def __init__(self):
            self.names = []

        def call(self, name, args):
            self.names.append(name)
            return "{}"

        def close(self):
            pass

    inner = Inner()
    agent_app.PrefixedBackend(inner, "tariffagent-mcp___").call("hts_search", {"text": "x"})
    assert inner.names == ["tariffagent-mcp___hts_search"]
    tf = (TF / "main.tf").read_text()
    assert 'mcp_tool_prefix = "${local.gateway_target}___"' in tf


def test_sigv4_signs_locally_with_fake_credentials(monkeypatch):
    httpx2 = pytest.importorskip("httpx2")
    pytest.importorskip("botocore")
    from botocore.credentials import Credentials

    monkeypatch.syspath_prepend(str(AWS))
    from agentcore_agent.sigv4 import SigV4Auth

    auth = SigV4Auth("us-east-1", credentials=Credentials("AKIATESTTESTTEST", "secret"))
    req = httpx2.Request(
        "POST", "https://gw.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp", json={"a": 1}
    )
    signed = next(auth.auth_flow(req))
    a = signed.headers["authorization"]
    assert a.startswith("AWS4-HMAC-SHA256 Credential=AKIATESTTESTTEST/")
    assert "/us-east-1/bedrock-agentcore/aws4_request" in a
    assert "x-amz-date" in signed.headers


# ---- Smoke test -----------------------------------------------------------------------


def test_smoke_test_products_and_remote_guard(monkeypatch):
    sys.path.insert(0, str(DEPLOY))
    import smoke_test

    assert len(smoke_test.PRODUCTS) == 5
    assert all(re.fullmatch(r"\d\d", p["chapter"]) for p in smoke_test.PRODUCTS)
    monkeypatch.delenv("I_ACCEPT_CLOUD_COSTS", raising=False)
    smoke_test.guard("http://127.0.0.1:18000/mcp")  # local is allowed
    with pytest.raises(SystemExit):
        smoke_test.guard("https://example.a.run.app/mcp")


# ---- GCP ------------------------------------------------------------------------------


def test_cloud_run_service_spec_is_private_and_scales_to_zero():
    yaml = pytest.importorskip("yaml")
    text = (GCP / "service.yaml").read_text()
    svc = yaml.safe_load(text)
    tmpl = svc["spec"]["template"]
    assert tmpl["metadata"]["annotations"]["autoscaling.knative.dev/minScale"] == "0"
    assert tmpl["spec"]["containers"][0]["ports"][0]["containerPort"] == 8080
    for f in (GCP / "service.yaml", GCP / "deploy.sh"):
        body = f.read_text()
        assert not re.search(r"--member[= ]\"?(allUsers|allAuthenticatedUsers)", body)
        assert "allAuthenticatedUsers" not in body
    assert "roles/run.invoker" in (GCP / "deploy.sh").read_text()


def _adk(code: str) -> subprocess.CompletedProcess:
    if not ADK_PY.exists():
        pytest.skip("deploy/gcp/.venv missing (created by make build-deploy-gcp)")
    if not (GCP / "tariff_adk" / "_assets.json").exists():
        pytest.skip("tariff_adk/_assets.json missing (deploy/gcp/build_assets.py writes it)")
    env = dict(os.environ, PYTHONPATH=f"{GCP}:{GCP / 'local_validation'}", MCP_AUTH="none")
    return subprocess.run([str(ADK_PY), "-c", code], env=env, capture_output=True, text=True, timeout=120)


def test_adk_agent_tree_builds_with_scripted_models():
    r = _adk(
        "from scripted_llm import scripted_models\n"
        "from tariff_adk.agent import build_root_agent, build_app, MAX_ADVOCATES\n"
        "root = build_root_agent(models=scripted_models(), mcp_url='http://127.0.0.1:9/mcp')\n"
        "names = [a.name for a in root.sub_agents]\n"
        "assert names == ['orchestrator', 'advocates', 'adjudicator'], names\n"
        "assert len(root.sub_agents[1].sub_agents) == MAX_ADVOCATES\n"
        "assert root.sub_agents[0].output_key == 'plan' and root.sub_agents[2].output_key == 'classification'\n"
        "assert build_app(root).context_cache_config is not None\n"
        "print('ok')\n"
    )
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-2000:]


def test_adk_id_token_headers_and_pickling():
    r = _adk(
        "import pickle\n"
        "from tariff_adk.auth import IdTokenHeaders, audience_for\n"
        "assert audience_for('https://svc-abc.a.run.app/mcp') == 'https://svc-abc.a.run.app'\n"
        "calls = []\n"
        "def fetch(aud):\n"
        "    calls.append(aud); return 'x.eyJleHAiOiA0MTAyNDQ0ODAwfQ.y'\n"
        "h = IdTokenHeaders('https://svc-abc.a.run.app', fetch=fetch)\n"
        "assert h() == {'Authorization': 'Bearer x.eyJleHAiOiA0MTAyNDQ0ODAwfQ.y'}\n"
        "h(); assert calls == ['https://svc-abc.a.run.app'], calls\n"
        "pickle.loads(pickle.dumps(IdTokenHeaders('https://a.run.app')))\n"
        "print('ok')\n"
    )
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-2000:]


def test_adk_default_models_are_claude_on_vertex_without_calls():
    r = _adk(
        "import os\n"
        "os.environ['GOOGLE_CLOUD_PROJECT_ID'] = 'test-project'\n"
        "from tariff_adk.agent import default_models\n"
        "m = default_models()\n"
        "assert type(m['adjudicator']).__name__ == 'Claude'\n"
        "assert m['adjudicator'].model.endswith('/publishers/anthropic/models/claude-sonnet-5'), m['adjudicator'].model\n"
        "assert m['advocate'].model.endswith('claude-haiku-4-5@20251001'), m['advocate'].model\n"
        "print('ok')\n"
    )
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-2000:]
