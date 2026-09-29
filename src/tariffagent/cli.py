"""Command line entry point: `uv run tariffagent ...`."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True, add_completion=False)
data_app = typer.Typer(no_args_is_help=True, help="Data ingestion and status")
app.add_typer(data_app, name="data")
console = Console()


@data_app.command("hts")
def data_hts(refresh: bool = False):
    """Fetch the current HTS release, notes, GRI and past basic editions."""
    from tariffagent.data import hts

    console.print(hts.ingest(refresh=refresh))


@data_app.command("cross-meta")
def data_cross_meta(start_year: int = 1989):
    """Harvest CROSS metadata (dates, codes, cross references) for all rulings."""
    from datetime import date

    from tariffagent.data import cross

    console.print(cross.harvest_meta(start=date(start_year, 1, 1)))


@data_app.command("cross-text")
def data_cross_text(since: str = "2025-07-01", limit: int = 0):
    """Load mirror texts, then fetch missing full texts from CROSS since a date."""
    from tariffagent.data import cross

    console.print(cross.load_mirror())
    ids = cross.ids_needing_text(since)
    if limit:
        ids = ids[:limit]
    console.print(f"fetching {len(ids)} rulings")
    console.print(cross.fetch_texts(ids))


@data_app.command("derive")
def data_derive():
    """Derive ruling status, crosswalk and the search indexes."""
    from tariffagent.data import status
    from tariffagent.data.db import connect
    from tariffagent.index.search import build_embeddings, build_fts

    con = connect()
    console.print({"status": status.derive_all(con)})
    console.print(build_fts(con))
    console.print(build_embeddings(con))


@data_app.command("status")
def data_status(as_json: bool = False):
    """Print counts, date ranges, stale-code rate and status distribution."""
    from tariffagent.data.report import data_report

    rep = data_report()
    if as_json:
        print(json.dumps(rep, indent=2))
        return
    t = Table(title="Customs Court data status")
    t.add_column("item")
    t.add_column("value")
    for k, v in rep.items():
        t.add_row(k, json.dumps(v) if isinstance(v, dict | list) else str(v))
    console.print(t)


eval_app = typer.Typer(no_args_is_help=True, help="Evaluation runs")
app.add_typer(eval_app, name="eval")


@eval_app.command("run")
def eval_run(
    dataset: str = typer.Option(..., help="dev_100, atlas_test_200, fresh_N, subset_N"),
    arm: str = typer.Option(
        "A", help="A single, B token-matched, C smart friend, D multi-agent, Z zero-shot"
    ),
    mode: str = typer.Option("batch", help="batch or interactive"),
    n: int = typer.Option(0, help="first n items (0 = all)"),
    run_id: str = typer.Option("", help="defaults to dataset-arm-timestamp"),
    phase: str = typer.Option("eval", help="ledger phase label"),
    concurrency: int = 4,
    repeat: int = 0,
    token_budget: int = 0,
    max_turns: int = 0,
    ask_mode: bool = typer.Option(False, help="abstain with questions when a missing fact decides the code"),
    checks: bool = typer.Option(True, help="checked final step with one repair turn"),
    items_from: str = typer.Option("", help="restrict to the item ids of another dataset, e.g. subset_80"),
):
    """Run one arm on one dataset and write results, traces and a report."""
    import os

    os.environ["PHASE"] = phase
    from tariffagent.evals.run import run_arm, summarize

    kw: dict = {"ask_mode": ask_mode, "checks": checks}
    if token_budget:
        kw["token_budget"] = token_budget
    if max_turns:
        kw["max_turns"] = max_turns
    item_ids = None
    if items_from:
        from tariffagent.evals.datasets import load_dataset

        item_ids = [it["item_id"] for it in load_dataset(items_from)]
    rep = run_arm(
        dataset,
        arm,
        mode=mode,
        n=n or None,
        run_id=run_id or None,
        concurrency=concurrency,
        repeat=repeat,
        item_ids=item_ids,
        **kw,
    )
    console.print(summarize(rep))


@eval_app.command("judge")
def eval_judge(run_id: str, second_judge: bool = True, phase: str = "judge"):
    """Reference-grounded reasoning judge on one run, validated by proxy and a second judge (kappa)."""
    import os

    os.environ["PHASE"] = phase
    from tariffagent.evals.analysis import judge_and_validate

    out = judge_and_validate(run_id, second=second_judge)
    console.print({k: v for k, v in out.items() if k != "verdicts"})


@eval_app.command("compare")
def eval_compare(
    dataset: str,
    runs: str = typer.Option(..., help="label=run_id pairs, comma separated; the first is the base"),
    name: str = typer.Option(..., help="report name, written to evals/reports/<name>.json"),
):
    """Paired bootstrap comparison of arms on one dataset, with slices. Offline."""
    from tariffagent.evals.analysis import compare
    from tariffagent.evals.run import REPORTS

    pairs = dict(x.split("=", 1) for x in runs.split(","))
    out = compare(pairs, dataset)
    (REPORTS / f"{name}.json").write_text(json.dumps(out, indent=2))
    console.print(json.dumps(out["arms"], indent=1)[:4000])


@eval_app.command("taxonomy")
def eval_taxonomy(run_id: str):
    """Failure distribution by level and by tagged cause. Offline."""
    from tariffagent.evals.run import REPORTS, load_run
    from tariffagent.evals.taxonomy import distribution, load_tags

    _, scored, _ = load_run(run_id)
    out = {"run_id": run_id, **distribution(scored, load_tags(run_id))}
    (REPORTS / f"{run_id}.taxonomy.json").write_text(json.dumps(out, indent=2))
    console.print(out)


@eval_app.command("smoke")
def eval_smoke():
    """Score recorded runs offline (no network, no spend) and check the reports are reproducible."""
    from tariffagent.evals.smoke import smoke

    smoke()


@app.command("cost")
def cost(report: bool = typer.Option(False, help="also write evals/reports/cost_summary.json")):
    """Print API spend by phase and model from data/ledger.jsonl."""
    from tariffagent.ledger import print_cost, savings_report

    print_cost()
    if report:
        from tariffagent.evals.run import REPORTS

        (REPORTS / "cost_summary.json").write_text(json.dumps(savings_report(), indent=2))
        console.print("wrote evals/reports/cost_summary.json")


if __name__ == "__main__":
    app()
