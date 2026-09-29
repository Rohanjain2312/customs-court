"""Build Customs Court replay files from recorded eval traces.

    uv run python scripts/make_replays.py                  # build demo/replays/*.jsonl from exhibits.json
    uv run python scripts/make_replays.py list RUN_ID      # show a run's items and scores, to pick exhibits
    uv run python scripts/make_replays.py record-fixture   # re-record the fixture source traces (offline)

The selection lives in demo/replays/exhibits.json. Each entry names a run (evals/runs/<run_id>)
or a traces file, one item_id, and how the exhibit is shown. The format of the output files
is described in demo/replays/README.md.

Nothing here calls a paid API. record-fixture runs with OFFLINE=true against
tests/fixtures/data: the handbag run replays recorded model responses, and the
entries marked placeholder use a scripted stand-in model with the real tools.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY_DIR = ROOT / "demo" / "replays"
CONFIG = REPLAY_DIR / "exhibits.json"
SOURCES = REPLAY_DIR / "sources"
RUNS = ROOT / "evals" / "runs"
DATASETS = ROOT / "evals" / "datasets"
FORMAT_VERSION = 1
GENERATOR = "scripts/make_replays.py"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def by_item(path: Path) -> dict[str, dict]:
    return {r["item_id"]: r for r in read_jsonl(path) if "item_id" in r}


_datasets: dict[str, tuple[str, dict]] | None = None


def dataset_row(item_id: str) -> tuple[str, dict]:
    global _datasets
    if _datasets is None:
        _datasets = {}
        for p in sorted(DATASETS.glob("*.jsonl")):
            for r in read_jsonl(p):
                _datasets.setdefault(r["item_id"], (p.stem, r))
    return _datasets.get(item_id, ("", {}))


def fmt_gold(code: str) -> str:
    d = "".join(c for c in code or "" if c.isdigit())
    return ".".join(p for p in (d[:4], d[4:6], d[6:8], d[8:10]) if p) if len(d) > 4 else d


def excerpt(text: str, n: int = 700) -> str:
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(". ", 1)[0]
    return (cut if len(cut) > n // 2 else text[:n]).rstrip(".") + "."


def recorded_cost(events: list[dict], result: dict) -> dict:
    last = next((e for e in reversed(events) if e.get("type") == "cost_update"), None) or {}
    tin = last.get("input_tokens", 0) + last.get("cache_read_tokens", 0) + last.get("cache_write_tokens", 0)
    return {
        "usd": round(result.get("usd", last.get("usd", 0.0)) or 0.0, 6),
        "input_tokens": last.get("input_tokens", 0),
        "output_tokens": last.get("output_tokens", 0),
        "cache_read_tokens": last.get("cache_read_tokens", 0),
        "cache_write_tokens": last.get("cache_write_tokens", 0),
        "tokens": result.get("tokens", tin + last.get("output_tokens", 0)),
        "calls": result.get("calls", last.get("calls", 0)),
        "cache_hit_rate": last.get("cache_hit_rate", 0.0),
        "tool_calls": result.get("tool_calls", sum(1 for e in events if e.get("type") == "tool_call")),
        "api_latency_s": result.get("api_latency_s"),
        "wall_s": result.get("wall_s"),
        "events": len(events),
    }


def build_one(entry: dict, order: int) -> tuple[dict, list[dict]]:
    from tariffagent.agents.events import EventAdapter

    item_id = entry["item_id"]
    if entry.get("traces"):
        traces_path = ROOT / entry["traces"]
        results_path = ROOT / entry.get("results", entry["traces"].replace(".traces.", ".results."))
        scored_path = None
        run_id = entry.get("run_id", traces_path.stem)
    else:
        run_id = entry["run_id"]
        traces_path = RUNS / run_id / "traces.jsonl"
        results_path = RUNS / run_id / "results.jsonl"
        scored_path = RUNS / run_id / "scored.jsonl"
    trace = by_item(traces_path).get(item_id)
    if not trace:
        raise SystemExit(f"{entry['exhibit_id']}: item {item_id} not found in {traces_path}")
    result = by_item(results_path).get(item_id, {})
    scored = by_item(scored_path).get(item_id, {}) if scored_path else {}
    ds_name, ds = dataset_row(entry.get("dataset_item", item_id))

    events = []
    for e in trace["events"]:
        events.append(EventAdapter.validate_python(e).model_dump())
    start = next((e for e in events if e["type"] == "run_start"), {})
    arm = start.get("arm", result.get("arm", ""))
    agent = "multi" if arm == "D" else "single"
    ruling = next((e for e in reversed(events) if e["type"] == "ruling"), None)
    pred = ((ruling or {}).get("classification") or {}).get("hts10", "")

    gold = entry.get("gold_code") or ds.get("gold_code") or scored.get("gold", "")
    meta = {
        "type": "meta",
        "format": FORMAT_VERSION,
        "exhibit_id": entry["exhibit_id"],
        "title": entry["title"],
        "description": start.get("description") or ds.get("description", ""),
        "blurb": entry.get("blurb", ""),
        "kind": entry.get("kind", "exhibit"),
        "mystery": bool(entry.get("mystery", False)),
        "agent": agent,
        "arm": arm,
        "models": start.get("models", {}),
        "pair": entry.get("pair") or item_id,
        "order": order,
        "objection_of": entry.get("objection_of"),
        "fact_change": entry.get("fact_change", ""),
        "timemachine": entry.get("timemachine"),
        "placeholder": bool(entry.get("placeholder", False)),
        "placeholder_note": entry.get("placeholder_note", ""),
        "note": entry.get("note", ""),
        "gold_code": fmt_gold(gold) if gold else "",
        "gold_digits": "".join(c for c in gold if c.isdigit()),
        "gold_stale": ds.get("code_stale"),
        "ruling_id": entry.get("ruling_id") or ds.get("ruling_id", ""),
        "ruling_date": entry.get("ruling_date") or ds.get("ruling_date", ""),
        "reference_excerpt": entry.get("reference_excerpt") or excerpt(ds.get("reference_reasoning", "")),
        "outcome": {
            "pred": pred,
            **{k: scored.get(k) for k in ("exact_10", "exact_8", "exact_6", "exact_4", "stale") if scored},
        },
        "recorded": recorded_cost(events, result),
        "source": {
            "run_id": run_id,
            "item_id": item_id,
            "dataset": ds_name or entry.get("dataset", ""),
            "traces": str(traces_path.relative_to(ROOT)),
        },
        "generated_by": GENERATOR,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return meta, events


def cmd_build(args) -> None:
    cfg = json.loads(CONFIG.read_text())
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    written = set()
    ids = [e["exhibit_id"] for e in cfg["exhibits"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("exhibit_id values in exhibits.json must be unique")
    for n, entry in enumerate(cfg["exhibits"]):
        if entry.get("skip"):
            continue
        meta, events = build_one(entry, n)
        out = REPLAY_DIR / f"{entry['exhibit_id']}.jsonl"
        with out.open("w") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        written.add(out.name)
        tag = "mystery" if meta["mystery"] else meta["kind"]
        print(
            f"{out.relative_to(ROOT)}: {len(events)} events, {meta['agent']}, {tag}, "
            f"pred {meta['outcome']['pred'] or '-'} gold {meta['gold_code'] or '-'}"
            + (" [placeholder]" if meta["placeholder"] else "")
        )
    # Remove replays this script generated earlier that are no longer in the config.
    for p in REPLAY_DIR.glob("*.jsonl"):
        if p.name in written:
            continue
        try:
            first = json.loads(p.open().readline())
        except Exception:  # noqa: BLE001
            continue
        if first.get("generated_by") == GENERATOR:
            p.unlink()
            print(f"removed stale {p.relative_to(ROOT)}")
    print(f"{len(written)} replays written")


def cmd_list(args) -> None:
    run = RUNS / args.run_id
    traces = by_item(run / "traces.jsonl")
    scored = by_item(run / "scored.jsonl")
    for iid, t in traces.items():
        s = scored.get(iid, {})
        ev = t["events"]
        types = {e["type"] for e in ev}
        _, ds = dataset_row(iid)
        print(
            f"{iid:28s} gold {s.get('gold', '-'):14s} pred {s.get('pred', '-'):14s} "
            f"e10={s.get('exact_10')} e6={s.get('exact_6')} ${s.get('usd', 0):.4f} "
            f"{len(ev)} ev {'multi' if 'advocate_done' in types else 'single'} | {ds.get('description', '')[:70]}"
        )


# ---------------------------------------------------------------------------
# record-fixture: offline source traces for the handbag exhibits
# ---------------------------------------------------------------------------

HANDBAG = (
    "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, two shoulder straps "
    "and a polyester lining. Retail value about $45."
)
PVC_FACT = "The outer surface is PVC plastic sheeting, not leather."
HANDBAG_PVC = (
    "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, two shoulder straps "
    "and a polyester lining. Retail value about $45.\n\nCorrection to the facts, which overrides anything "
    f"above: {PVC_FACT}"
)
PLACEHOLDER = "[Scripted placeholder, not a model run.]"


def _resp(content, stop="end_turn", tin=0, tout=0):
    from tariffagent.ledger import Usage
    from tariffagent.llm.base import LLMResponse

    return LLMResponse(
        content=content,
        stop_reason=stop,
        usage=Usage(input_tokens=tin, output_tokens=tout),
        model="scripted-placeholder",
        provider="scripted",
        usd=0.0,
    )


def _tool(name, args, i):
    return {"type": "tool_use", "id": f"s{i}", "name": name, "input": args}


def _text(obj):
    return [{"type": "text", "text": json.dumps(obj)}]


def scripted_objection(req):
    """Stand-in model for the PVC handbag objection. Real tools, scripted reasoning."""
    turn = sum(1 for m in req.messages if m["role"] == "assistant") + 1
    if turn == 1:
        return _resp(
            [_tool("hts_search", {"text": "handbag outer surface of plastic sheeting PVC"}, 1)],
            "tool_use",
            900,
            60,
        )
    if turn == 2:
        return _resp(
            [
                _tool("hts_navigate", {"code": "4202.22"}, 2),
                _tool("cross_search", {"query": "handbag outer surface PVC plastic sheeting"}, 3),
            ],
            "tool_use",
            1400,
            80,
        )
    # A scripted answer cites no ruling: only a real model run may claim a precedent.
    cited: list[dict] = []
    return _resp(
        _text(
            {
                "hts10": "4202.22.15.00",
                "facts": {
                    "material": "Outer surface of PVC plastic sheeting (per the objection); polyester lining",
                    "function": "Carries personal effects",
                    "form": "Handbag with zipper closure and two shoulder straps",
                    "end_use": "Personal use",
                },
                "gri_path": [
                    "GRI 1: heading 4202 names handbags.",
                    "GRI 6: 4202.22 covers an outer surface of sheeting of plastics or of textile materials.",
                    "GRI 6: 4202.22.15 is the line for an outer surface of sheeting of plastics.",
                ],
                "deciding_gri": "GRI 1",
                "cited_rulings": cited,
                "rejected_alternatives": [
                    {
                        "code": "4202.21.90.00",
                        "reason": "Covers an outer surface of leather. After the objection the outer surface is PVC sheeting.",
                    },
                    {
                        "code": "4202.22.81.00",
                        "reason": "Covers an outer surface of textile materials. PVC sheeting is plastics, not textile.",
                    },
                ],
                "missing_facts": [
                    "Whether the PVC sheeting has a textile backing that shows on the outer surface"
                ],
                "confidence": 0.8,
                "abstain": False,
                "rationale": f"{PLACEHOLDER} Heading 4202 names handbags, so GRI 1 settles the heading. "
                "With the outer surface changed to PVC sheeting, subheading 4202.22 applies, and line "
                "4202.22.15 covers an outer surface of sheeting of plastics.",
            }
        ),
        "end_turn",
        2100,
        420,
    )


MEMOS = {
    "4202": {
        "argument": f"{PLACEHOLDER} Heading 4202 names handbags in its text. Under GRI 1 a heading that names "
        "the article comes first. The outer surface is leather, so 4202.21 applies, and the $45 value "
        "puts it on the line for handbags valued over $20 each.",
        "best_code": "4202.21.90.00",
        "exclusions_against": ["If the outer surface were plastics or textile, 4202.22 would apply instead."],
        "strength": 0.9,
    },
    "4205": {
        "argument": f"{PLACEHOLDER} Heading 4205 covers other articles of leather. The bag is made of leather, "
        "so 4205 is a fallback if no heading names the article.",
        "best_code": "4205.00.80.00",
        "exclusions_against": [
            "4205 is residual. It applies only to leather articles not covered by a more specific heading, "
            "and 4202 names handbags."
        ],
        "strength": 0.15,
    },
}


def scripted_multi(req):
    """Stand-in models for the multi-agent handbag hearing. Real tools, scripted reasoning."""
    p = req.purpose
    turn = sum(1 for m in req.messages if m["role"] == "assistant") + 1
    if p.startswith("orchestrator"):
        if turn == 1:
            return _resp([_tool("hts_search", {"text": "leather handbag"}, 1)], "tool_use", 800, 40)
        return _resp(
            _text(
                {
                    "facts": {
                        "material": "Cowhide leather outer surface; polyester lining",
                        "function": "Carries personal effects",
                        "form": "Handbag with zipper and two shoulder straps",
                        "end_use": "Personal use",
                    },
                    "missing_facts": [
                        "Exact unit value",
                        "Whether any trim covers most of the outer surface",
                    ],
                    "candidate_headings": ["4202", "4205"],
                    "reasoning": f"{PLACEHOLDER} Handbag of leather: 4202 names it, 4205 is the residual.",
                }
            ),
            "end_turn",
            1200,
            160,
        )
    if p.startswith("advocate-"):
        h = p.split(":")[0].split("-")[1]
        if turn == 1:
            return _resp([_tool("get_notes", {"scope": "chapter", "id": "42"}, 2)], "tool_use", 1500, 50)
        if turn == 2:
            return _resp(
                [_tool("cross_search", {"query": f"leather handbag heading {h}"}, 3)], "tool_use", 2600, 50
            )
        m = MEMOS.get(h, MEMOS["4205"])
        memo = {
            "heading": h,
            "best_code": m["best_code"],
            "argument": m["argument"],
            "supporting_rulings": [],
            "exclusions_against": m["exclusions_against"],
            "strength": m["strength"],
        }
        return _resp(_text(memo), "end_turn", 3100, 260)
    # Adjudicator.
    if turn == 1:
        return _resp([_tool("hts_navigate", {"code": "4202.21.90.00"}, 4)], "tool_use", 2400, 40)
    return _resp(
        _text(
            {
                "hts10": "4202.21.90.00",
                "facts": {
                    "material": "Cowhide leather outer surface; polyester lining",
                    "function": "Carries personal effects",
                    "form": "Handbag with zipper and two shoulder straps",
                    "end_use": "Personal use",
                },
                "gri_path": [
                    "GRI 1: heading 4202 names handbags; 4205 is residual and gives way.",
                    "GRI 6: 4202.21 covers an outer surface of leather.",
                    "GRI 6: 4202.21.90 is the line for handbags valued over $20 each.",
                ],
                "deciding_gri": "GRI 1",
                "cited_rulings": [],
                "rejected_alternatives": [
                    {"code": "4205.00.80.00", "reason": "Residual heading. 4202 names handbags."},
                    {
                        "code": "4202.21.60.00",
                        "reason": "For handbags valued not over $20 each. This one is about $45.",
                    },
                ],
                "missing_facts": ["Exact unit value, if it could be $20 or less"],
                "confidence": 0.85,
                "abstain": False,
                "rationale": f"{PLACEHOLDER} The 4202 advocate showed that the heading names handbags, so GRI 1 "
                "decides the heading and 4205 gives way. The outer surface is leather and the value is over "
                "$20, which gives 4202.21.90.00.",
            }
        ),
        "end_turn",
        3300,
        380,
    )


def cmd_record_fixture(args) -> None:
    fixture = ROOT / "tests" / "fixtures" / "data"
    os.environ.update(
        {
            "OFFLINE": "true",
            "DATA_DIR": str(fixture),
            "USE_VECTORS": "false",
            "LEDGER_FILE": str(Path(tempfile.mkdtemp(prefix="cc-ledger-")) / "ledger.jsonl"),
        }
    )
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from tariffagent import config

    config.get_settings.cache_clear()
    from tariffagent.agents.events import EventBus
    from tariffagent.agents.multi import MultiConfig, multi_episode
    from tariffagent.agents.runner import drive
    from tariffagent.agents.single import AgentConfig, single_episode
    from tariffagent.agents.tooling import InProcessBackend, ToolExecutor
    from tariffagent.mcp_server.tools.core import TariffTools

    assert config.get_settings().offline, "record-fixture must run offline"
    tools = TariffTools(use_vectors=False, redact_eval=False)
    SOURCES.mkdir(parents=True, exist_ok=True)
    tpath, rpath = SOURCES / "fixture.traces.jsonl", SOURCES / "fixture.results.jsonl"
    traces, results = by_item(tpath), by_item(rpath)

    def keep(item_id: str, res: dict, bus: EventBus) -> None:
        traces[item_id] = {"item_id": item_id, "events": [e.model_dump() for e in bus.events]}
        results[item_id] = {k: v for k, v in res.items() if k != "events"}
        c = (res.get("classification") or {}).get("hts10")
        print(f"recorded {item_id}: {len(bus.events)} events -> {c}")

    # 1. The real recorded run: replays the fixture response cache, zero spend.
    item = {"item_id": "fixture_handbag", "description": HANDBAG}
    bus = EventBus("fixture:fixture_handbag")
    cfg = AgentConfig.for_arm("A", run_id="demo-fixture", max_turns=8)
    try:
        res = drive(single_episode(item, cfg, ToolExecutor(InProcessBackend(tools), bus), bus))
        keep("fixture_handbag", res, bus)
    except Exception as e:  # noqa: BLE001
        print(
            f"fixture_handbag not recorded ({type(e).__name__}: {str(e)[:160]}). The fixture response "
            "cache does not match the current prompts; the previous source trace is kept.",
            file=sys.stderr,
        )

    # 2. Placeholder objection: same bag, outer surface changed to PVC. Scripted model.
    item = {"item_id": "fixture_handbag_pvc", "description": HANDBAG_PVC}
    bus = EventBus("placeholder:fixture_handbag_pvc")
    cfg = AgentConfig.for_arm("A", run_id="demo-placeholder", max_turns=8)
    res = drive(
        single_episode(item, cfg, ToolExecutor(InProcessBackend(tools), bus), bus), scripted_objection
    )
    keep("fixture_handbag_pvc", res, bus)

    # 3. Placeholder multi-agent hearing of the leather bag. Scripted models.
    item = {"item_id": "fixture_handbag_multi", "description": HANDBAG}
    bus = EventBus("placeholder:fixture_handbag_multi")
    mcfg = MultiConfig.default(run_id="demo-placeholder")
    res = drive(multi_episode(item, mcfg, tools, bus), scripted_multi)
    keep("fixture_handbag_multi", res, bus)

    for path, rows in ((tpath, traces), (rpath, results)):
        with path.open("w") as f:
            for r in rows.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {tpath.relative_to(ROOT)} and {rpath.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("build", help="build demo/replays/*.jsonl from exhibits.json (default)")
    lp = sub.add_parser("list", help="list the items of one run")
    lp.add_argument("run_id")
    sub.add_parser("record-fixture", help="re-record the fixture source traces (offline, no spend)")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "record-fixture":
        cmd_record_fixture(args)
    else:
        cmd_build(args)


if __name__ == "__main__":
    main()
