"""Upload the code and data an HF Job needs to a private Hugging Face dataset repo.

    uv run python scripts/hf_job/push_bundle.py

Code: `git archive HEAD` (commit first). Data: the frozen SQLite corpus, the local
vector index and the ATLAS link files. The repo is private. Storage is included in
the PRO plan; nothing here is billed.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
REPO = "rohanjain2312/customs-court-evaljobs"


def main() -> None:
    api = HfApi()
    api.create_repo(REPO, repo_type="dataset", private=True, exist_ok=True)
    info = api.repo_info(REPO, repo_type="dataset")
    assert info.private, "bundle repo must be private"
    with tempfile.TemporaryDirectory() as td:
        tar = Path(td) / "code.tar.gz"
        subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(tar), "HEAD"], cwd=ROOT, check=True)
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
        api.upload_file(
            path_or_fileobj=str(tar),
            path_in_repo="bundle/code.tar.gz",
            repo_id=REPO,
            repo_type="dataset",
            commit_message=f"code {sha}",
        )
    data = ROOT / "data"
    files = [
        data / "tariffagent.sqlite",
        data / "atlas_test_200_links.json",
        data / "atlas_validation_200_links.json",
    ]
    files += sorted((data / "index").glob("*"))
    for f in files:
        if f.is_file():
            api.upload_file(
                path_or_fileobj=str(f),
                path_in_repo=f"bundle/data/{f.relative_to(data)}",
                repo_id=REPO,
                repo_type="dataset",
                commit_message=f"data {f.name}",
            )
            print("uploaded", f.relative_to(ROOT))
    print("bundle ready at", REPO, "(private)")


if __name__ == "__main__":
    main()
