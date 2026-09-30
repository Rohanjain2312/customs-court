"""Run an agent arm on a dataset and write results, traces and a report.

Every report records the config hash, git sha, seed, model ids and dataset sha256.
Runs always use --redact-eval so tools cannot return the golden rulings.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime

from tariffagent.agents.events import EventBus
from tariffagent.agents.runner import run_batched, run_interactive
from tariffagent.agents.single import AgentConfig, single_episode
from tariffagent.agents.tooling import ToolExecutor, item_as_of
from tariffagent.config import ROOT, get_settings
from tariffagent.evals.datasets import MANIFEST, load_dataset
from tariffagent.evals.metrics import score_run
from tariffagent.evals.stats import bootstrap_ci
from tariffagent.mcp_server.tools.core import TariffTools

RUNS = ROOT / "evals" / "runs"
REPORTS = ROOT / "evals" / "reports"
SEED = 13


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def make_factory(arm: str, cfg: AgentConfig, tools: TariffTools):
    def make(item: dict):
        bus = EventBus(f"{cfg.run_id}:{item['item_id']}")
        if arm == "D":
            from tariffagent.agents.multi import MultiConfig, multi_episode

            mcfg = MultiConfig.default(run_id=cfg.run_id, **cfg.extra)
            return multi_episode(item, mcfg, tools, bus), bus
        ex = ToolExecutor(tools, bus, agent="single", as_of=item_as_of(item)) if cfg.use_tools else None
        return single_episode(item, cfg, ex, bus), bus

    return make


def run_arm(
    dataset: str,
    arm: str,
    mode: str = "batch",
    n: int | None = None,
    run_id: str | None = None,
    concurrency: int = 4,
    item_ids: list[str] | None = None,
    repeat: int = 0,
    **overrides,
) -> dict:
    os.environ["REDACT_EVAL"] = "true"
    get_settings.cache_clear()
    s = get_settings()
    items = load_dataset(dataset)
    if item_ids:
        wanted = set(item_ids)
        items = [it for it in items if it["item_id"] in wanted]
    if n:
        items = items[:n]
    run_id = run_id or f"{dataset}-{arm}-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    cfg = AgentConfig.for_arm(
        arm if arm != "D" else "A", run_id=run_id, **{k: v for k, v in overrides.items() if k != "extra"}
    )
    cfg.extra = overrides.get("extra", {})
    if repeat:
        # Repeat runs differ only by a marker in the request, so they are not served from the response cache.
        cfg.extra = {**cfg.extra, "repeat": repeat}
    if mode == "batch":
        cfg.cache_ttl = "1h"
    tools = TariffTools(redact_eval=True)
    factory = make_factory(arm, cfg, tools)
    started = datetime.now(UTC)
    if mode == "batch":
        results = run_batched(factory, items)
    else:
        results = run_interactive(factory, items, concurrency=concurrency)
    out_dir = RUNS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w") as f, (out_dir / "traces.jsonl").open("w") as tf:
        for r in results:
            tf.write(json.dumps({"item_id": r["item_id"], "events": r.get("events", [])}) + "\n")
            f.write(json.dumps({k: v for k, v in r.items() if k != "events"}) + "\n")
    rows, agg = score_run(items, results)
    with (out_dir / "scored.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    cis = {}
    for k in ("exact_10", "exact_8", "exact_6", "exact_4", "exact_2"):
        cis[k] = bootstrap_ci([r[k] for r in rows if r[k] is not None], seed=SEED)
    man = json.loads(MANIFEST.read_text())
    report = {
        "run_id": run_id,
        "dataset": dataset,
        "dataset_sha256": man[dataset]["sha256"],
        "arm": arm,
        "mode": mode,
        "n_items": len(items),
        "repeat": repeat,
        "git_sha": git_sha(),
        "config_hash": s.fingerprint(),
        "seed": SEED,
        "models": {
            "main": cfg.model,
            "friend": cfg.friend_model,
            "reasoner": s.reasoner_model,
            "advocate": s.advocate_model,
        },
        "agent_config": {k: v for k, v in cfg.__dict__.items() if k != "extra"} | {"extra": cfg.extra},
        "redact_eval": True,
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now(UTC).isoformat(timespec="seconds"),
        "metrics": agg,
        "ci95": cis,
        "latency_note": "Batch runs have no meaningful per-item latency; see interactive runs for p50 and p95."
        if mode == "batch"
        else "",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{run_id}.json").write_text(json.dumps(report, indent=2))
    return report


def summarize(report: dict) -> str:
    m, c = report["metrics"], report["ci95"]

    def f(k):
        x = c.get(k, {})
        return f"{x.get('mean')} [{x.get('lo')}, {x.get('hi')}] n={x.get('n')}"

    return (
        f"{report['run_id']} arm={report['arm']} n={report['n_items']}\n"
        f"  acc10 {f('exact_10')}\n  acc8  {f('exact_8')}\n  acc6  {f('exact_6')}\n  acc4  {f('exact_4')}\n"
        f"  abstain {m['abstain_rate']} acc_when_answering {m['acc_when_answering']} ece {m['ece']}\n"
        f"  citations {m['citations_total']} valid_rate {m['citation_valid_rate']} halluc {m['citation_hallucinated']}\n"
        f"  usd/item {m['usd_per_item']} total {m['usd_total']} tokens/item {m['tokens_per_item']} "
        f"tools/item {m['tool_calls_per_item']} cache_hit {m['cache_hit_rate']} p50 {m['latency_p50_s']} p95 {m['latency_p95_s']} errors {m['n_errors']}"
    )


def load_run(run_id: str) -> tuple[list[dict], list[dict], dict]:
    d = RUNS / run_id
    results = [json.loads(line) for line in (d / "results.jsonl").open()]
    scored = [json.loads(line) for line in (d / "scored.jsonl").open()]
    report = json.loads((REPORTS / f"{run_id}.json").read_text())
    return results, scored, report


def traces(run_id: str) -> dict[str, list[dict]]:
    p = RUNS / run_id / "traces.jsonl"
    return (
        {json.loads(line)["item_id"]: json.loads(line)["events"] for line in p.open()} if p.exists() else {}
    )
