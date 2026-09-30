"""Start, watch and collect Hugging Face Jobs that run the open-model evals.

    uv run python scripts/hf_job/launch.py run --tag check1 --plan check --flavor cpu-upgrade --timeout 30m
    uv run python scripts/hf_job/launch.py run --tag gpu1 --plan A,D,freshA --flavor rtx-pro-6000 --timeout 43m
    uv run python scripts/hf_job/launch.py status JOB_ID
    uv run python scripts/hf_job/launch.py fetch --tag gpu1

Jobs are paid from the PRO plan's included monthly compute credits. The account has no
payment method (whoami-v2 canPay=false), so a job stops when the credits are used up and
nothing is billed. `--timeout` caps each job's run time as a second guard.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, get_token, hf_hub_download

ROOT = Path(__file__).resolve().parents[2]
REPO = "rohanjain2312/customs-court-evaljobs"
IMAGE = "vllm/vllm-openai:latest"

BOOT = (
    "python3 -c \"from huggingface_hub import hf_hub_download as d; "
    f"d('{REPO}', 'bundle/code.tar.gz', repo_type='dataset', local_dir='/boot')\" && "
    "tar xzf /boot/bundle/code.tar.gz -C /boot scripts/hf_job/job.sh && bash /boot/scripts/hf_job/job.sh"
)


def run(a) -> None:
    api = HfApi()
    minutes = int(a.timeout.rstrip("m"))
    job = api.run_job(
        image=IMAGE,
        command=["bash", "-c", BOOT],
        env={"JOB_TAG": a.tag, "JOB_PLAN": a.plan, "JOB_DEADLINE_MIN": str(max(5, minutes - 3)), "BUNDLE_REPO": REPO},
        secrets={"HF_TOKEN": get_token()},
        flavor=a.flavor,
        timeout=a.timeout,
        name=f"customs-court-{a.tag}",
    )
    print(job.id, job.status.stage, job.flavor)


def status(a) -> None:
    api = HfApi()
    j = api.inspect_job(job_id=a.job_id)
    print(j.status.stage, j.status.message or "")
    if a.logs:
        for line in api.fetch_job_logs(job_id=a.job_id):
            print(line)


def fetch(a) -> None:
    """Download a job's state and merge it: cache files, runs, reports, ledger rows, logs."""
    p = hf_hub_download(REPO, f"results/{a.tag}/state.tar.gz", repo_type="dataset", force_download=True)
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(p) as t:
            t.extractall(td, filter="data")
        src = Path(td)
        for sub in ("data/cache", "evals/runs", "evals/reports", "evals/taxonomy"):
            if (src / sub).exists():
                shutil.copytree(src / sub, ROOT / sub, dirs_exist_ok=True)
        logs = ROOT / "data" / "logs" / f"hfjob-{a.tag}"
        if (src / "logs").exists():
            shutil.copytree(src / "logs", logs, dirs_exist_ok=True)
        led = src / "data" / "ledger.jsonl"
        if led.exists():
            seen = set((ROOT / "data" / "ledger.jsonl").read_text().splitlines())
            new = [ln for ln in led.read_text().splitlines() if ln and ln not in seen]
            with (ROOT / "data" / "ledger.jsonl").open("a") as f:
                for ln in new:
                    f.write(ln + "\n")
            print(f"ledger: +{len(new)} rows (all $0, local models)")
    reports = sorted(x.name for x in (ROOT / "evals" / "reports").glob("os-*.json"))
    print("merged; open-model reports:", json.dumps(reports))


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--tag", required=True)
    r.add_argument("--plan", required=True)
    r.add_argument("--flavor", default="rtx-pro-6000")
    r.add_argument("--timeout", default="43m")
    s = sp.add_parser("status")
    s.add_argument("job_id")
    s.add_argument("--logs", action="store_true")
    f = sp.add_parser("fetch")
    f.add_argument("--tag", required=True)
    a = ap.parse_args()
    {"run": run, "status": status, "fetch": fetch}[a.cmd](a)


if __name__ == "__main__":
    main()
