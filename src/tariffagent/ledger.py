"""Spend ledger and budget enforcement.

Every real model call appends one line to data/ledger.jsonl using the usage the
provider reported. Budget checks read the ledger before each call and fail closed.
"""

from __future__ import annotations

import fcntl
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tariffagent.config import get_settings, price_for


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0

    @property
    def total_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_read_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
        )

    def add(self, other: Usage) -> None:
        for k in asdict(self):
            setattr(self, k, getattr(self, k) + getattr(other, k))


def cost_usd(model: str, u: Usage, batch: bool = False) -> float:
    p = price_for(model)
    d = (
        u.input_tokens * p.input
        + u.output_tokens * p.output
        + u.cache_read_tokens * p.cache_read
        + u.cache_write_5m_tokens * p.cache_write_5m
        + u.cache_write_1h_tokens * p.cache_write_1h
    ) / 1e6
    return d * (p.batch_discount if batch else 1.0)


@dataclass
class LedgerEntry:
    ts: str
    phase: str
    run_id: str
    provider: str
    model: str
    purpose: str
    batch: bool
    usage: dict
    usd: float
    latency_s: float = 0.0
    extra: dict = field(default_factory=dict)


def _path() -> Path:
    p = get_settings().ledger_path
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_entries(path: Path | None = None) -> list[dict]:
    p = path or _path()
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def spent(run_id: str | None = None, day: str | None = None) -> float:
    total = 0.0
    for e in read_entries():
        if run_id and e["run_id"] != run_id:
            continue
        if day and not e["ts"].startswith(day):
            continue
        total += e["usd"]
    return total


def check_budget(run_id: str, projected_usd: float = 0.0) -> None:
    """Raise BudgetExceeded if spending projected_usd would break any cap."""
    s = get_settings()
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    checks = [
        ("total", spent(), s.budget_usd_total),
        ("per_day", spent(day=today), s.budget_usd_per_day),
        ("per_run", spent(run_id=run_id), s.budget_usd_per_run),
    ]
    for name, used, cap in checks:
        if used + projected_usd > cap:
            raise BudgetExceeded(
                f"Budget {name} would be exceeded: spent ${used:.4f} + projected ${projected_usd:.4f} > cap ${cap:.2f}"
            )


def record(
    *,
    provider: str,
    model: str,
    usage: Usage,
    run_id: str,
    purpose: str,
    batch: bool = False,
    latency_s: float = 0.0,
    extra: dict | None = None,
) -> LedgerEntry:
    s = get_settings()
    e = LedgerEntry(
        ts=datetime.now(UTC).isoformat(timespec="seconds"),
        phase=s.phase,
        run_id=run_id,
        provider=provider,
        model=model,
        purpose=purpose,
        batch=batch,
        usage=asdict(usage),
        usd=round(cost_usd(model, usage, batch), 6),
        latency_s=round(latency_s, 3),
        extra=extra or {},
    )
    p = _path()
    with p.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(asdict(e)) + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)
    return e


def summary() -> dict:
    by_phase: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)
    by_phase_model: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"usd": 0.0, "calls": 0, "usage": Usage()}
    )
    total = 0.0
    for e in read_entries():
        by_phase[e["phase"]] += e["usd"]
        by_model[e["model"]] += e["usd"]
        row = by_phase_model[(e["phase"], e["model"])]
        row["usd"] += e["usd"]
        row["calls"] += 1
        row["usage"].add(Usage(**e["usage"]))
        total += e["usd"]
    return {"total": total, "by_phase": dict(by_phase), "by_model": dict(by_model), "rows": by_phase_model}


def print_cost() -> None:
    from rich.console import Console
    from rich.table import Table

    s = get_settings()
    sm = summary()
    t = Table(title="API spend by phase and model (from data/ledger.jsonl)")
    for c in ("phase", "model", "calls", "in", "out", "cache read", "cache write", "USD"):
        t.add_column(c, justify="right" if c not in ("phase", "model") else "left")
    for (phase, model), r in sorted(sm["rows"].items()):
        u: Usage = r["usage"]
        t.add_row(
            phase,
            model,
            str(r["calls"]),
            f"{u.input_tokens:,}",
            f"{u.output_tokens:,}",
            f"{u.cache_read_tokens:,}",
            f"{u.cache_write_5m_tokens + u.cache_write_1h_tokens:,}",
            f"${r['usd']:.4f}",
        )
    c = Console()
    c.print(t)
    for k, v in sorted(sm["by_phase"].items()):
        c.print(f"phase {k}: ${v:.4f}")
    for k, v in sorted(sm["by_model"].items()):
        c.print(f"model {k}: ${v:.4f}")
    c.print(f"[bold]TOTAL: ${sm['total']:.4f} of ${s.budget_usd_total:.2f} cap[/bold]")


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.elapsed = time.perf_counter() - self.t0


def savings_report() -> dict:
    """Actual spend vs the same tokens at list price with no prompt caching and no batch discount.

    Counterfactuals use the recorded token counts: every cached or cache-written token is
    priced as plain input. This ignores that uncached calls could have been shaped differently,
    so it measures the pricing effect of caching and batching on the calls that were made.
    """
    from tariffagent.config import price_for

    out: dict = {"by_phase": {}, "total": {}}

    def add(bucket: dict, e: dict) -> None:
        u = e["usage"]
        p = price_for(e["model"])
        all_in = (
            u["input_tokens"] + u["cache_read_tokens"] + u["cache_write_5m_tokens"] + u["cache_write_1h_tokens"]
        )
        list_usd = (all_in * p.input + u["output_tokens"] * p.output) / 1e6
        disc = p.batch_discount if e.get("batch") else 1.0
        b = bucket
        b["actual_usd"] = b.get("actual_usd", 0.0) + e["usd"]
        b["no_cache_same_mode_usd"] = b.get("no_cache_same_mode_usd", 0.0) + list_usd * disc
        b["no_cache_no_batch_usd"] = b.get("no_cache_no_batch_usd", 0.0) + list_usd
        b["calls"] = b.get("calls", 0) + 1
        b["cache_read_tokens"] = b.get("cache_read_tokens", 0) + u["cache_read_tokens"]
        b["input_tokens_all"] = b.get("input_tokens_all", 0) + all_in

    for e in read_entries():
        add(out["by_phase"].setdefault(e.get("phase", ""), {}), e)
        add(out["total"], e)
    for b in [out["total"], *out["by_phase"].values()]:
        for k in list(b):
            if k.endswith("_usd"):
                b[k] = round(b[k], 4)
        b["cache_read_share"] = round(b["cache_read_tokens"] / max(1, b["input_tokens_all"]), 4)
        b["saving_vs_no_cache_no_batch"] = round(1 - b["actual_usd"] / max(1e-9, b["no_cache_no_batch_usd"]), 4)
    return out
