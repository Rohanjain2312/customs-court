"""HTS tree data for the D3 view: root -> sections -> chapters -> headings -> lines.

Headings and lines come from TariffTools.hts_navigate. Sections and chapters are not
rows in the HTS table, so their names live here (short forms of the official titles).
"""

from __future__ import annotations

from tariffagent.data.hts import SECTIONS, digits, format_code
from tariffagent.mcp_server.tools.core import TariffTools

CHAPTERS: dict[str, str] = {
    "01": "Live animals",
    "02": "Meat and edible meat offal",
    "03": "Fish and crustaceans, molluscs and other aquatic invertebrates",
    "04": "Dairy produce; birds' eggs; natural honey",
    "05": "Products of animal origin, not elsewhere specified",
    "06": "Live trees and other plants; cut flowers",
    "07": "Edible vegetables and certain roots and tubers",
    "08": "Edible fruit and nuts; peel of citrus fruit or melons",
    "09": "Coffee, tea, mate and spices",
    "10": "Cereals",
    "11": "Products of the milling industry; malt; starches",
    "12": "Oil seeds and oleaginous fruits; industrial or medicinal plants",
    "13": "Lac; gums, resins and other vegetable saps and extracts",
    "14": "Vegetable plaiting materials",
    "15": "Animal, vegetable or microbial fats and oils",
    "16": "Preparations of meat, fish or crustaceans",
    "17": "Sugars and sugar confectionery",
    "18": "Cocoa and cocoa preparations",
    "19": "Preparations of cereals, flour, starch or milk; bakers' wares",
    "20": "Preparations of vegetables, fruit, nuts or other parts of plants",
    "21": "Miscellaneous edible preparations",
    "22": "Beverages, spirits and vinegar",
    "23": "Residues from the food industries; prepared animal feed",
    "24": "Tobacco and manufactured tobacco substitutes",
    "25": "Salt; sulfur; earths and stone; plastering materials, lime and cement",
    "26": "Ores, slag and ash",
    "27": "Mineral fuels, mineral oils; bituminous substances; mineral waxes",
    "28": "Inorganic chemicals",
    "29": "Organic chemicals",
    "30": "Pharmaceutical products",
    "31": "Fertilizers",
    "32": "Tanning or dyeing extracts; dyes, pigments, paints and inks",
    "33": "Essential oils and resinoids; perfumery, cosmetic or toilet preparations",
    "34": "Soap, washing preparations, lubricants, waxes, candles",
    "35": "Albuminoidal substances; modified starches; glues; enzymes",
    "36": "Explosives; pyrotechnic products; matches",
    "37": "Photographic or cinematographic goods",
    "38": "Miscellaneous chemical products",
    "39": "Plastics and articles thereof",
    "40": "Rubber and articles thereof",
    "41": "Raw hides and skins (other than furskins) and leather",
    "42": "Articles of leather; handbags and similar containers",
    "43": "Furskins and artificial fur; manufactures thereof",
    "44": "Wood and articles of wood; wood charcoal",
    "45": "Cork and articles of cork",
    "46": "Manufactures of straw, esparto or other plaiting materials",
    "47": "Pulp of wood or other fibrous cellulosic material",
    "48": "Paper and paperboard; articles of paper pulp",
    "49": "Printed books, newspapers, pictures and other printed products",
    "50": "Silk",
    "51": "Wool, fine or coarse animal hair; horsehair yarn and woven fabric",
    "52": "Cotton",
    "53": "Other vegetable textile fibers; paper yarn",
    "54": "Man-made filaments",
    "55": "Man-made staple fibers",
    "56": "Wadding, felt and nonwovens; special yarns; twine, cordage",
    "57": "Carpets and other textile floor coverings",
    "58": "Special woven fabrics; tufted fabrics; lace; tapestries",
    "59": "Impregnated, coated, covered or laminated textile fabrics",
    "60": "Knitted or crocheted fabrics",
    "61": "Apparel, knitted or crocheted",
    "62": "Apparel, not knitted or crocheted",
    "63": "Other made up textile articles; worn clothing; rags",
    "64": "Footwear, gaiters and the like",
    "65": "Headgear and parts thereof",
    "66": "Umbrellas, walking sticks, whips",
    "67": "Prepared feathers; artificial flowers; articles of human hair",
    "68": "Articles of stone, plaster, cement, asbestos, mica",
    "69": "Ceramic products",
    "70": "Glass and glassware",
    "71": "Pearls, precious stones and metals; imitation jewelry; coin",
    "72": "Iron and steel",
    "73": "Articles of iron or steel",
    "74": "Copper and articles thereof",
    "75": "Nickel and articles thereof",
    "76": "Aluminum and articles thereof",
    "78": "Lead and articles thereof",
    "79": "Zinc and articles thereof",
    "80": "Tin and articles thereof",
    "81": "Other base metals; cermets",
    "82": "Tools, implements, cutlery, spoons and forks, of base metal",
    "83": "Miscellaneous articles of base metal",
    "84": "Nuclear reactors, boilers, machinery and mechanical appliances",
    "85": "Electrical machinery and equipment; sound and TV recorders",
    "86": "Railway or tramway locomotives, rolling stock and track fixtures",
    "87": "Vehicles other than railway or tramway rolling stock",
    "88": "Aircraft, spacecraft, and parts thereof",
    "89": "Ships, boats and floating structures",
    "90": "Optical, photographic, measuring, medical instruments",
    "91": "Clocks and watches and parts thereof",
    "92": "Musical instruments; parts and accessories",
    "93": "Arms and ammunition; parts and accessories",
    "94": "Furniture; bedding; lamps; prefabricated buildings",
    "95": "Toys, games and sports requisites",
    "96": "Miscellaneous manufactured articles",
    "97": "Works of art, collectors' pieces and antiques",
    "98": "Special classification provisions",
    "99": "Temporary legislation; additional import restrictions",
}


def _level(d: str) -> str:
    return {2: "chapter", 4: "heading", 6: "subheading", 8: "tariff_item", 10: "statistical"}.get(
        len(d), "line"
    )


def _chapters_present(tools: TariffTools) -> set[str]:
    rows = tools._q("SELECT DISTINCT chapter FROM hts_rows WHERE rev=?", tools.rev)
    return {r["chapter"] for r in rows if r["chapter"]}


def _section_of(ch: int) -> tuple[str, int, int, str] | None:
    for s in SECTIONS:
        if s[1] <= ch <= s[2]:
            return s
    return None


def node(tools: TariffTools, code: str) -> dict | None:
    """One tree node with its parent and children. `code` is 'root', 'S-XI' or HTS digits."""
    code = (code or "").strip()
    present = _chapters_present(tools)
    if code.lower() in ("", "root"):
        kids = []
        for sec, a, b, title in SECTIONS:
            chs = [f"{c:02d}" for c in range(a, b + 1) if f"{c:02d}" in present]
            if chs:
                kids.append(
                    {
                        "code": f"S-{sec}",
                        "description": f"Section {sec}: {title}",
                        "is_leaf": False,
                        "level": "section",
                        "range": [a, b],
                    }
                )
        return {
            "code": "root",
            "description": "Harmonized Tariff Schedule of the United States",
            "level": "root",
            "revision": tools.rev,
            "parent": None,
            "children": kids,
        }
    if code.upper().startswith("S-"):
        sec = code[2:].upper()
        match = next((s for s in SECTIONS if s[0] == sec), None)
        if not match:
            return None
        _, a, b, title = match
        kids = [
            {
                "code": f"{c:02d}",
                "description": CHAPTERS.get(f"{c:02d}", f"Chapter {c}"),
                "is_leaf": False,
                "level": "chapter",
            }
            for c in range(a, b + 1)
            if f"{c:02d}" in present
        ]
        return {
            "code": f"S-{sec}",
            "description": f"Section {sec}: {title}",
            "level": "section",
            "revision": tools.rev,
            "parent": {"code": "root", "description": "HTSUS"},
            "children": kids,
        }
    d = digits(code)
    if not d or len(d) > 10:
        return None
    nav = tools.hts_navigate(d)
    if not nav.found:
        return None
    if len(d) == 2:
        s = _section_of(int(d))
        parent = {"code": f"S-{s[0]}", "description": f"Section {s[0]}: {s[3]}"} if s else None
        desc = CHAPTERS.get(d, f"Chapter {d}")
        this_code = d
    elif nav.node:
        parent = (
            {"code": nav.parent.code, "description": nav.parent.description}
            if nav.parent
            else {"code": d[:2], "description": CHAPTERS.get(d[:2], "")}
        )
        desc = nav.node.description
        this_code = nav.node.code
    else:
        # No separate line for this prefix: hts_navigate listed the lines under it.
        parent = {"code": d[:4] if len(d) > 4 else d[:2], "description": ""}
        desc = nav.message
        this_code = format_code(d)
    children = [
        {
            "code": c.code,
            "description": c.description,
            "is_leaf": bool(c.is_leaf),
            "level": _level(digits(c.code)),
        }
        for c in nav.children
    ]
    return {
        "code": this_code,
        "description": desc,
        "level": _level(d),
        "revision": tools.rev,
        "parent": parent,
        "children": children,
    }
