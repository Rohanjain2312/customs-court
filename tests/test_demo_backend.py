"""Customs Court demo backend (demo/backend/app.py). No network, no spend.

Replays come from demo/replays. HTS endpoints use the fixture DB (conftest sets DATA_DIR).
Live-mode tests use a scripted model through the `complete` hook, so no provider is called.
"""

import json

import pytest
from fastapi.testclient import TestClient

from tariffagent.agents.events import EventAdapter
from tariffagent.ledger import Usage
from tariffagent.llm.base import LLMResponse


def _app(monkeypatch, mode="replay", key="", cap=None, complete=None):
    from tariffagent import config

    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setenv("OFFLINE", "true")
    if cap is not None:
        monkeypatch.setenv("DEMO_SESSION_CAP_USD", str(cap))
    config.get_settings.cache_clear()
    from demo.backend.app import create_app

    return TestClient(create_app(mode=mode, complete=complete))


def _sse(text: str) -> list[dict]:
    out = []
    for block in text.split("\n\n"):
        data = [ln[5:].lstrip() for ln in block.splitlines() if ln.startswith("data:")]
        if data:
            out.append(json.loads("\n".join(data)))
    return out


def test_health_and_config(monkeypatch):
    c = _app(monkeypatch)
    h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["mode"] == "replay" and h["exhibits"] >= 10
    cfg = c.get("/api/config").json()
    assert cfg["mode"] == "replay" and cfg["live"] is False
    assert cfg["session_cap_usd"] == 2.0
    assert "compressed" in cfg["timing_note"]


def test_exhibits_list_seals_mystery_rulings(monkeypatch):
    ex = _app(monkeypatch).get("/api/exhibits").json()
    assert len(ex) >= 10
    mystery = [e for e in ex if e["mystery"]]
    assert mystery
    for e in mystery:
        assert "gold_code" not in e and "outcome" not in e and e["sealed"] is True
    kinds = {e["kind"] for e in ex}
    assert {"exhibit", "objection", "timemachine"} <= kinds
    obj = next(e for e in ex if e["kind"] == "objection")
    base = next(e for e in ex if e["exhibit_id"] == obj["objection_of"])
    assert obj["exhibit_id"] in base["objections"]


def test_reveal_returns_the_sealed_code(monkeypatch):
    c = _app(monkeypatch)
    mid = next(e["exhibit_id"] for e in c.get("/api/exhibits").json() if e["mystery"])
    r = c.get(f"/api/exhibits/{mid}/reveal").json()
    assert len("".join(ch for ch in r["gold_code"] if ch.isdigit())) >= 8


def test_replay_stream_parses_into_typed_events(monkeypatch):
    c = _app(monkeypatch)
    for eid in ("polivac-film", "polivac-film-multi"):
        r = c.get(f"/api/replay/{eid}?speed=0")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        msgs = _sse(r.text)
        assert msgs[-1]["type"] == "done"
        events = [EventAdapter.validate_python(m) for m in msgs[:-1]]
        types = [e.type for e in events]
        assert types[0] == "run_start" and "ruling" in types and "tree_focus" in types
        # Compressed clock: never runs backwards, no gap longer than the cap.
        ts = [e.t for e in events]
        assert all(b >= a for a, b in zip(ts, ts[1:], strict=False))
        assert max(b - a for a, b in zip(ts, ts[1:], strict=False)) <= 1.5 + 1e-6


def test_replay_splits_long_chunks_without_changing_text(monkeypatch):
    from demo.backend.app import ROOT
    from demo.backend.replays import ReplayStore, schedule

    rep = ReplayStore(ROOT / "demo" / "replays").get("polivac-film-multi")
    orig = "".join(e["text"] for e in rep.events() if e["type"] == "adjudicator_chunk")
    sent = [ev for _, ev in schedule(rep.events()) if ev["type"] == "adjudicator_chunk"]
    assert len(sent) > 1
    assert "".join(e["text"] for e in sent) == orig


def test_schedule_caps_long_batch_gaps():
    from demo.backend.replays import schedule

    evs = [
        {"type": "run_start", "t": 0.0},
        {"type": "tool_call", "t": 300.0},
        {"type": "tree_focus", "t": 300.0},
        {"type": "ruling", "t": 900.0},
    ]
    plan = schedule(evs, max_gap=1.5)
    assert [round(d, 2) for d, _ in plan] == [0.0, 1.5, 0.16, 1.5]
    assert plan[-1][1]["t_orig"] == 900.0


def test_unknown_replay_is_404(monkeypatch):
    r = _app(monkeypatch).get("/api/replay/nope")
    assert r.status_code == 404 and "error" in r.json()


def test_hts_tree_endpoints_on_fixture_db(monkeypatch):
    c = _app(monkeypatch)
    root = c.get("/api/hts/root").json()
    sec = next(ch for ch in root["children"] if ch["code"] == "S-VIII")
    assert sec["range"] == [41, 43]
    chapters = c.get("/api/hts/S-VIII").json()["children"]
    assert any(ch["code"] == "42" for ch in chapters)
    head = c.get("/api/hts/4202").json()
    assert head["code"] == "4202" and head["parent"]["code"] == "42"
    codes = [ch["code"] for ch in head["children"]]
    assert "4202.21" in codes
    line = c.get("/api/hts/4202.21").json()
    assert "4202.21.90.00" in [ch["code"] for ch in line["children"]]
    assert c.get("/api/hts/9999").status_code == 404


def test_time_machine_endpoints(monkeypatch):
    c = _app(monkeypatch)
    revs = c.get("/api/revisions").json()
    assert revs["current"] and len(revs["revisions"]) >= 2
    d = c.get("/api/hts-diff", params={"code": "4202.21.90.00", "rev_a": "2018"}).json()
    assert d["change"] in {"unchanged", "rate_changed", "description_changed", "added", "removed"}
    assert d["rev_a"].startswith("2018")


def test_replay_objection_points_to_the_recorded_rehearing(monkeypatch):
    c = _app(monkeypatch)
    r = c.post("/api/objection", json={"exhibit_id": "handbag-leather"}).json()
    assert r["mode"] == "replay" and r["exhibit_id"] == "handbag-pvc-objection" and "PVC" in r["fact_change"]
    none = c.post("/api/objection", json={"exhibit_id": "polivac-film", "fact_change": "x"})
    assert none.status_code == 404


def test_replay_mode_refuses_live_calls(monkeypatch):
    c = _app(monkeypatch, mode="replay", key="sk-test-not-used")
    r = c.post("/api/classify", json={"description": "A leather handbag with two straps"})
    assert r.status_code == 403 and "Replay mode" in r.json()["error"]


def test_live_mode_refuses_without_a_key(monkeypatch):
    c = _app(monkeypatch, mode="live", key="")
    cfg = c.get("/api/config").json()
    assert cfg["live"] is False and "ANTHROPIC_API_KEY" in cfg["live_reason"]
    r = c.post("/api/classify", json={"description": "A leather handbag with two straps"})
    assert r.status_code == 403 and "ANTHROPIC_API_KEY" in r.json()["error"]
    p = c.post("/api/describe-photo", json={"image": "data:image/png;base64,AAAA"})
    assert p.status_code == 403


FINAL = {
    "hts10": "4202.21.90.00",
    "facts": {"material": "leather", "function": "carry", "form": "bag", "end_use": "personal"},
    "gri_path": ["GRI 1: heading 4202 names handbags.", "GRI 6: 4202.21.90.00."],
    "deciding_gri": "GRI 1",
    "cited_rulings": [],
    "rejected_alternatives": [{"code": "4202.21.60.00", "reason": "valued over $20"}],
    "missing_facts": [],
    "confidence": 0.8,
    "abstain": False,
    "rationale": "Heading 4202 names handbags.",
}


class Scripted:
    """A fake model: one tool call, then the final answer. Counts calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, req):
        self.calls += 1
        first = sum(1 for m in req.messages if m["role"] == "assistant") == 0
        if first:
            content = [{"type": "tool_use", "id": "t1", "name": "hts_navigate", "input": {"code": "4202.21"}}]
            stop = "tool_use"
        else:
            content, stop = [{"type": "text", "text": json.dumps(FINAL)}], "end_turn"
        return LLMResponse(
            content=content,
            stop_reason=stop,
            usage=Usage(input_tokens=100, output_tokens=20),
            model=req.model,
            provider="fake",
            usd=0.001,
        )


def test_live_classify_streams_events_and_counts_spend(monkeypatch):
    fake = Scripted()
    c = _app(monkeypatch, mode="live", key="sk-test-not-used", complete=fake)
    assert c.get("/api/config").json()["live"] is True
    r = c.post(
        "/api/classify", json={"description": "Women's handbag of cowhide leather, $45", "arm": "single"}
    )
    assert r.status_code == 200
    msgs = _sse(r.text)
    assert msgs[-1]["type"] == "done"
    events = [EventAdapter.validate_python(m) for m in msgs[:-1]]
    ruling = next(e for e in events if e.type == "ruling")
    assert ruling.classification["hts10"] == "4202.21.90.00"
    assert any(e.type == "tool_call" for e in events)
    assert fake.calls >= 2
    assert msgs[-1]["session_spent_usd"] == pytest.approx(0.001 * fake.calls)
    assert c.get("/api/config").json()["session_spent_usd"] == pytest.approx(0.001 * fake.calls)


def test_live_session_cap_stops_the_hearing_before_any_call(monkeypatch):
    fake = Scripted()
    c = _app(monkeypatch, mode="live", key="sk-test-not-used", cap=0.0001, complete=fake)
    r = c.post("/api/classify", json={"description": "Women's handbag of cowhide leather, $45"})
    msgs = _sse(r.text)
    errors = [m for m in msgs if m["type"] == "error"]
    assert errors and "cap" in errors[0]["message"].lower()
    assert fake.calls == 0


def test_live_objection_builds_a_changed_description(monkeypatch):
    c = _app(monkeypatch, mode="live", key="sk-test-not-used", complete=Scripted())
    r = c.post(
        "/api/objection", json={"exhibit_id": "handbag-leather", "fact_change": "The outer surface is PVC."}
    ).json()
    assert r["mode"] == "live" and r["description"].endswith("The outer surface is PVC.")


def test_live_mode_replays_the_recorded_fixture_offline(monkeypatch):
    """The real provider path with OFFLINE=true: served only from the fixture response cache."""
    c = _app(monkeypatch, mode="live", key="sk-test-not-used")
    from tests.test_agent_e2e import HANDBAG

    r = c.post("/api/classify", json={"description": HANDBAG, "arm": "single"})
    msgs = _sse(r.text)
    errors = [m["message"] for m in msgs if m["type"] == "error"]
    if any("OfflineMiss" in e for e in errors):
        pytest.skip("fixture response cache does not match the current prompts; re-record it")
    assert not errors, errors
    ruling = next(m for m in msgs if m["type"] == "ruling")
    assert ruling["classification"]["hts10"].startswith("4202")
    # Cached responses cost nothing in this session.
    assert msgs[-1]["session_spent_usd"] == 0.0
