"""Polite HTTP fetching with an on-disk raw cache, rate limiting and retries."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx

USER_AGENT = "customs-court-research/0.1 (+https://github.com/Rohanjain2312/customs-court)"


class PoliteClient:
    def __init__(self, raw_dir: Path, min_interval_s: float = 1.0, timeout: float = 120.0):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self._last = 0.0
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True
        )
        self.network_calls = 0

    def _wait(self) -> None:
        dt = time.monotonic() - self._last
        if dt < self.min_interval_s:
            time.sleep(self.min_interval_s - dt)
        self._last = time.monotonic()

    def cache_path(self, url: str, name: str | None = None) -> Path:
        if name:
            return self.raw_dir / name
        return self.raw_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".bin")

    def get_bytes(self, url: str, name: str | None = None, refresh: bool = False, retries: int = 4) -> bytes | None:
        """Return the body, reading from the raw cache when present. None on 404."""
        p = self.cache_path(url, name)
        if p.exists() and not refresh:
            return p.read_bytes()
        err: Exception | None = None
        for attempt in range(retries):
            self._wait()
            try:
                r = self.client.get(url)
                self.network_calls += 1
                if r.status_code == 404:
                    return None
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2**attempt * 2)
                    err = RuntimeError(f"HTTP {r.status_code} for {url}")
                    continue
                r.raise_for_status()
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(p.suffix + ".tmp")
                tmp.write_bytes(r.content)
                tmp.replace(p)
                return r.content
            except httpx.HTTPError as e:
                err = e
                time.sleep(2**attempt * 2)
        raise RuntimeError(f"Failed to fetch {url}: {err}")
