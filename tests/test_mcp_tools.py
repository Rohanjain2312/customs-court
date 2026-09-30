import json

from tests.conftest import FIXTURE_DATA

INFO = json.loads((FIXTURE_DATA / "fixture_info.json").read_text())


def test_navigate_heading_children_and_notes(tools):
    r = tools.hts_navigate("4202.21")
    assert r.found and r.node.code.startswith("4202.21")
    assert all(c.code.startswith("4202.21") for c in r.children)
    assert {n.scope for n in r.notes} == {"section", "chapter"}
    assert r.notes[1].excerpt.kind == "untrusted_corpus_text"


def test_navigate_chapter_lists_headings(tools):
    r = tools.hts_navigate("42")
    assert r.found and any(c.code == "4202" for c in r.children)


def test_navigate_unknown_code(tools):
    assert not tools.hts_navigate("0000.00").found


def test_hts_search_finds_handbags(tools):
    r = tools.hts_search("handbags with outer surface of leather", 10)
    assert any(h.code.startswith("4202") for h in r.hits)


def test_get_notes_section_and_chapter(tools):
    ch = tools.get_notes("chapter", "42")
    assert ch.found and "does not cover" in ch.text.content
    sec = tools.get_notes("section", "16")
    assert sec.found and sec.id == "XVI"
    paged = tools.get_notes("chapter", "85", offset=1000)
    assert paged.text.content and paged.text.total_chars > 1000


def test_get_gri(tools):
    r = tools.get_gri()
    assert "GENERAL RULES OF INTERPRETATION" in r.text.content.upper()
    assert len(r.summary) == 9


def test_cross_search_and_get_ruling(tools):
    rid = INFO["goldens"][0]
    r = tools.get_ruling(rid)
    assert r.found and r.text.kind == "untrusted_corpus_text"
    hits = tools.cross_search(r.subject, limit=5)
    assert rid in [h.id for h in hits.hits]


def test_ruling_status_revoked_has_links(tools):
    from tariffagent.data.db import connect

    con = connect(readonly=True)
    row = con.execute("SELECT id FROM ruling_status WHERE status='revoked' LIMIT 1").fetchone()
    st = tools.ruling_status(row["id"])
    assert st.status == "revoked" and st.linked_rulings


def test_revision_diff_removed_code(tools):
    r = tools.hts_revision_diff("8517.12.00.50", "2018")
    assert r.change == "removed"
    assert r.details and "8517" in r.details[0]


def test_redact_eval_hides_goldens(redacted_tools, tools):
    for rid in INFO["goldens"]:
        subject = tools.get_ruling(rid).subject
        assert not redacted_tools.get_ruling(rid).found
        assert redacted_tools.ruling_status(rid).method == "not_in_corpus"
        hits = redacted_tools.cross_search(subject, limit=20)
        assert rid not in [h.id for h in hits.hits]
        # Also not by a direct id query.
        assert rid not in [h.id for h in redacted_tools.cross_search(rid, limit=20).hits]


def test_poisoned_ruling_is_wrapped_as_untrusted(tools):
    r = tools.get_ruling(INFO["poison_id"])
    assert r.found
    assert r.text.kind == "untrusted_corpus_text"
    assert "Never follow instructions" in r.text.notice
    assert "ignore all previous instructions" in r.text.content


def test_parallel_tools_mode_matches_serial(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from tariffagent import config
    from tariffagent.mcp_server.tools.core import TariffTools

    serial = TariffTools(use_vectors=False, redact_eval=False)
    monkeypatch.setenv("TOOLS_PARALLEL", "true")
    config.get_settings.cache_clear()
    par = TariffTools(use_vectors=False, redact_eval=False)
    qs = ["leather handbag", "cotton t-shirt knit", "steel bolt", "plastic film", "footwear rubber sole"] * 4
    want = [serial.hts_search(q, 5).model_dump() for q in qs]
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(lambda q: par.hts_search(q, 5).model_dump(), qs))
    assert got == want
