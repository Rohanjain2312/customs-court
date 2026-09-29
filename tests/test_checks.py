"""The checked final step (agents/checks.py) on the fixture data. No model calls."""

import json

import pytest

from tariffagent.agents.checks import review
from tariffagent.agents.schemas import Classification
from tariffagent.agents.tooling import InProcessBackend


def _cls(code: str, **kw) -> Classification:
    base = {
        "hts10": code,
        "gri_path": ["GRI 1: heading text"],
        "deciding_gri": "GRI 1",
        "cited_rulings": [],
        "rejected_alternatives": [],
        "missing_facts": [],
        "confidence": 0.8,
        "abstain": False,
        "rationale": "Heading text covers it.",
    }
    base.update(kw)
    return Classification.model_validate(base)


@pytest.fixture
def run(tools):
    return InProcessBackend(tools).call


def test_valid_leaf_passes(run):
    assert review(_cls("4202.21.90.00"), run) == []


def test_nonexistent_suffix_lists_real_lines(run):
    problems = review(_cls("4202.21.90.99"), run)
    assert len(problems) == 1
    assert "not a line" in problems[0]
    assert "4202.21.90.00" in problems[0]


def test_short_code_is_rejected(run):
    assert "digits" in review(_cls("4202.21"), run)[0]


def test_parts_provision_requires_parts_rules(run, tools):
    # Find a 10-digit parts line in chapter 84 or 85 of the fixture.
    row = tools.con.execute(
        "SELECT code FROM hts_rows WHERE rev=? AND chapter IN ('84','85') AND is_leaf=1 "
        "AND length(digits)=10 AND lower(path) LIKE '%parts%' LIMIT 1",
        (tools.rev,),
    ).fetchone()
    assert row, "fixture has no parts line"
    problems = review(_cls(row["code"]), run)
    assert any("parts or accessories" in p and "Section XVI" in p for p in problems)
    # Naming the note clears the check.
    ok = _cls(row["code"], gri_path=["GRI 1 with Section XVI note 2(b): solely or principally used"])
    assert not any("parts or accessories" in p for p in review(ok, run))


def test_poisoned_ruling_cannot_be_cited(run, tools):
    st = json.loads(run("ruling_status", {"id": "N999001"}))
    assert "contains_instructions_to_ai" in st["flags"]
    problems = review(_cls("4202.21.90.00", cited_rulings=[{"id": "N999001", "status": "in_force"}]), run)
    assert any("instruct an AI model" in p for p in problems)


def test_injection_warning_on_search_hit(tools):
    res = tools.cross_search("women's handbag cowhide leather zipper shoulder straps", limit=10)
    hit = next(h for h in res.hits if h.id == "N999001")
    assert hit.snippet.injection_warning


def test_unknown_citation_is_rejected(run):
    problems = review(_cls("4202.21.90.00", cited_rulings=[{"id": "N000000", "status": "in_force"}]), run)
    assert any("not found" in p for p in problems)


def test_revoked_citation_names_replacement(run, tools):
    row = tools.con.execute(
        "SELECT s.id FROM ruling_status s JOIN rulings r ON r.id=s.id WHERE s.status='revoked' "
        "AND s.linked != '[]' LIMIT 1"
    ).fetchone()
    if not row:
        pytest.skip("fixture has no revoked ruling with a link")
    problems = review(_cls("4202.21.90.00", cited_rulings=[{"id": row["id"], "status": "in_force"}]), run)
    assert any("revoked" in p for p in problems)


def test_abstain_without_code_is_accepted(run):
    assert review(_cls("", abstain=True, missing_facts=["Is it knit or woven?"]), run) == []
