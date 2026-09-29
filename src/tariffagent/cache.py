"""On-disk response cache keyed by a hash of the full request.

Re-runs, crashes and report rebuilds read from here and cost nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from tariffagent.config import get_settings


def request_key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


class ResponseCache:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().cache_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        if p.exists():
            return json.loads(p.read_text())
        return None

    def put(self, key: str, value: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False))
        os.replace(tmp, p)
