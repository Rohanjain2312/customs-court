"""Offline smoke eval: no network, no spend.

1. Re-score every committed run in evals/runs/ from its saved results and check the
   headline metrics equal the committed report.
2. Replay the recorded fixture episode (skill + tools on the fixture DB) from the
   recorded response cache and check it still classifies.
"""

from __future__ import annotations

import json
import os

from rich.console import Console

from tariffagent.config import ROOT, get_settings

console = Console()
KEYS = ("acc_10", "acc_8", "acc_6", "acc_4", "acc_2", "usd_total", "citation_valid_rate")


def rescore_committed() -> int:
    from tariffagent.evals.datasets import load_dataset
    from tariffagent.evals.metrics import score_run
    from tariffagent.evals.run import REPORTS, RUNS

    have_db = get_settings().db_path.exists()
    keys = KEYS if have_db else tuple(k for k in KEYS if not k.startswith("citation"))
    bad = 0
    n = 0
    for d in sorted(RUNS.glob("*")):
        rp = REPORTS / f"{d.name}.json"
        if not (d / "results.jsonl").exists() or not rp.exists():
            continue
        report = json.loads(rp.read_text())
        items = load_dataset(report["dataset"])
        results = [json.loads(line) for line in (d / "results.jsonl").open()]
        ids = {r["item_id"] for r in results}
        items = [it for it in items if it["item_id"] in ids]
        _, agg = score_run(items, results, with_citations=have_db)
        diffs = {
            k: (report["metrics"].get(k), agg.get(k)) for k in keys if report["metrics"].get(k) != agg.get(k)
        }
        n += 1
        if diffs:
            bad += 1
            console.print(f"[red]MISMATCH[/red] {d.name}: {diffs}")
    console.print(f"re-scored {n} committed runs, {bad} mismatches")
    return bad


def replay_fixture() -> bool:
    os.environ.update(
        {"OFFLINE": "true", "DATA_DIR": str(ROOT / "tests" / "fixtures" / "data"), "USE_VECTORS": "false"}
    )
    get_settings.cache_clear()
    from tariffagent.agents.events import EventBus
    from tariffagent.agents.runner import drive
    from tariffagent.agents.single import AgentConfig, single_episode, system_blocks
    from tariffagent.agents.tooling import ToolExecutor
    from tariffagent.mcp_server.tools.core import TariffTools

    system_blocks.__globals__["_system_cache"].clear()
    item = {
        "item_id": "fixture_handbag",
        "description": "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, two shoulder "
        "straps and a polyester lining. Retail value about $45.",
    }
    cfg = AgentConfig.for_arm("A", run_id="test-poison", max_turns=8)
    bus = EventBus("smoke")
    res = drive(
        single_episode(item, cfg, ToolExecutor(TariffTools(use_vectors=False, redact_eval=False), bus), bus)
    )
    ok = bool(res.get("classification")) and res["classification"]["hts10"].startswith("4202")
    console.print(
        f"fixture replay: {res['classification']['hts10'] if ok else res}  ({'ok' if ok else 'FAILED'})"
    )
    return ok


def smoke() -> None:
    bad = rescore_committed()
    ok = replay_fixture()
    if bad or not ok:
        raise SystemExit(1)
    console.print("[green]eval-smoke passed[/green]")
