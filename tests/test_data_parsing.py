from tariffagent.data.atlas import parse_item
from tariffagent.data.cross import norm_id
from tariffagent.data.hts import build_rows, digits, format_code, html_to_text, section_for_chapter
from tariffagent.data.status import text_actions

RAW = [
    {"htsno": "0101", "indent": "0", "description": "Live horses, asses, mules and hinnies:"},
    {"htsno": "", "indent": "1", "description": "Horses:", "superior": "true"},
    {"htsno": "0101.21.00", "indent": "2", "description": "Purebred breeding animals", "general": "Free"},
    {"htsno": "0101.21.00.10", "indent": "3", "description": "Males", "units": ["No."]},
    {"htsno": "0101.21.00.20", "indent": "3", "description": "Females", "units": ["No."]},
    {"htsno": "0101.29.00", "indent": "2", "description": "Other", "general": "Free"},
    {"htsno": "0102", "indent": "0", "description": "Live bovine animals:"},
    {"htsno": "0102.21.00", "indent": "1", "description": "Purebred breeding animals"},
]


def test_build_rows_parents_and_paths():
    rows = build_rows("r1", RAW)
    by_code = {r["code"]: r for r in rows if r["code"]}
    males = by_code["0101.21.00.10"]
    assert rows[males["parent_idx"]]["code"] == "0101.21.00"
    assert "Horses:" in males["path"]
    assert males["is_leaf"] == 1
    assert by_code["0101.21.00"]["is_leaf"] == 0
    # "Other" under Horses keeps the superior row as parent.
    assert rows[by_code["0101.29.00"]["parent_idx"]]["description"] == "Horses:"
    # A new heading resets the stack.
    assert by_code["0102"]["parent_idx"] == -1
    assert rows[by_code["0102.21.00"]["parent_idx"]]["code"] == "0102"
    assert all(r["chapter"] == "01" and r["section"] == "I" for r in rows)


def test_code_helpers():
    assert digits("8471.30.01.00") == "8471300100"
    assert format_code("8471300100") == "8471.30.01.00"
    assert format_code("847130") == "8471.30"
    assert section_for_chapter(84) == "XVI"
    assert section_for_chapter(99) == "XXII"


def test_html_to_text_keeps_list_items_on_lines():
    t = html_to_text("<div>Notes</div><ul><li>1. First</li><li>2. Second</li></ul>")
    assert t.splitlines() == ["Notes", "1. First", "2. Second"]


def test_norm_id():
    assert norm_id("NY I84264") == "I84264"
    assert norm_id("HQ 967123") == "967123"
    assert norm_id("n364781") == "N364781"


def test_parse_atlas_item():
    obj = {
        "messages": [
            {"role": "user", "content": "What is the HTS US Code for a leather wallet?"},
            {
                "role": "assistant",
                "content": "HTS US Code -> 4202.31.6000\nReasoning -> Heading 4202 covers wallets.",
            },
        ]
    }
    it = parse_item(obj, "test", 3)
    assert it["description"] == "a leather wallet"
    assert it["gold_digits"] == "4202316000"
    assert it["reference_reasoning"].startswith("Heading 4202")
    assert it["item_id"] == "atlas_test_00003"


def test_text_actions_finds_revocations_and_skips_proposals():
    t = (
        "In accordance with 19 U.S.C. 1625(c), NY N123456 is hereby revoked. "
        "HQ 950000 is modified to reflect the proper classification. "
        "CBP proposed to revoke NY N999999 in the Customs Bulletin."
    )
    acts = text_actions(t)
    assert "N123456" in acts["revokes"]
    assert "950000" in acts["modifies"]
    assert "N999999" not in acts["revokes"]


def test_text_actions_skips_negated_and_denied_revocations():
    t = (
        "Although you indicate there are rulings which were not specifically revoked by CBP, such as HQ 964559. "
        "The branch denied the request for interim revocation of HQ H325434. "
        "RE: Revocation of NY N111111;"
    )
    acts = text_actions(t)
    assert "964559" not in acts["revokes"]
    assert "H325434" not in acts["revokes"]
    assert "N111111" in acts["revokes"]


def test_text_actions_v3_short_forms_and_month_may():
    t = (
        "Box 721 Medina, OH 44258 RE: HQ 088175 Revoked; "
        "EFFECT ON OTHER RULINGS: HQ 557046, dated May 17, 1993, is modified as to classification."
    )
    acts = text_actions(t)
    assert "088175" in acts["revokes"]
    assert "557046" in acts["modifies"]
