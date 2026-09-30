"""Binary, reference-grounded reasoning judge.

The judge compares the agent's legal reasoning with the CBP ruling's own analysis
and passes only if the agent reached its answer for the same legal reason. It runs
on the cheap model (Haiku 4.5, temperature 0, Message Batches). A second judge
from another vendor (gpt-5-mini) is used to measure agreement (Cohen's kappa).
Validation without human labels: a programmatic proxy (correct at 10 digits
should mostly pass; wrong at the chapter level should fail).
"""

from __future__ import annotations

import json
import re

from tariffagent.agents.runner import provider_for
from tariffagent.agents.single import parse_classification  # noqa: F401  (shared JSON helper)
from tariffagent.config import get_settings
from tariffagent.data.db import connect
from tariffagent.llm.base import LLMRequest

JUDGE_SYSTEM = """You grade the legal reasoning of a customs classification assistant against the reasoning of the official U.S. Customs and Border Protection (CBP) ruling for the same product.

PASS only if both hold:
1. The assistant's final heading (first 4 digits) is the same as the heading CBP chose.
2. The decisive legal basis is the same as CBP's: the same heading text, legal note, GRI (for example GRI 1 versus GRI 3(b)) or essential-character factor carried the decision. Wording can differ.

FAIL if the heading differs, if the assistant reached the right heading for a different or wrong legal reason, or if its reasoning contradicts the ruling's facts. Do not reward confident language. Differences only in the statistical suffix do not matter for this grade.

Reply with only JSON: {"verdict": "pass" or "fail", "reason": "one sentence"}"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]}, "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def legal_analysis(text: str, limit: int = 3500) -> str:
    """The part of a ruling that carries its reasoning (skip the address block)."""
    t = re.sub(r"\s+", " ", text or "")
    for marker in (
        "LAW AND ANALYSIS",
        "The applicable subheading",
        "applicable subheading",
        "In your letter",
    ):
        i = t.find(marker)
        if i > 0:
            start = max(0, i - 600) if marker != "In your letter" else i
            return t[start : start + limit]
    return t[:limit]


def reference_for(item: dict, links: dict[str, dict] | None = None) -> tuple[str, str]:
    """Return (reference text, source label). Prefer the linked ruling's text, else ATLAS reasoning."""
    con = connect(readonly=True)
    rid = item.get("ruling_id") or ((links or {}).get(item["item_id"], {}) or {}).get("ruling_id")
    score = ((links or {}).get(item["item_id"], {}) or {}).get("score", 1.0 if item.get("ruling_id") else 0)
    if rid and score >= 0.5:
        row = con.execute("SELECT text FROM rulings WHERE id=?", (rid,)).fetchone()
        if row and row["text"]:
            return (
                f"CBP ruling {rid}, gold code {item['gold_code']}:\n{legal_analysis(row['text'])}",
                f"ruling:{rid}",
            )
    if item.get("reference_reasoning"):
        return (
            f"Reasoning summarized from the CBP ruling (gold code {item['gold_code']}):\n{item['reference_reasoning'][:3000]}",
            "atlas_reasoning",
        )
    return "", "none"


def judge_request(item: dict, cls: dict, reference: str, model: str, run_id: str) -> LLMRequest:
    agent = {
        "code": cls.get("hts10"),
        "deciding_gri": cls.get("deciding_gri"),
        "gri_path": cls.get("gri_path"),
        "rationale": cls.get("rationale"),
        "rejected_alternatives": cls.get("rejected_alternatives"),
    }
    user = (
        f"<product>\n{item['description']}\n</product>\n\n<cbp_reference>\n{reference}\n</cbp_reference>\n\n"
        f"<assistant_answer>\n{json.dumps(agent, ensure_ascii=False)[:4000]}\n</assistant_answer>"
    )
    kw = {"temperature": 0.0} if "haiku" in model else {}
    # The judge compares reasoning; it needs no tools and a small answer.
    return LLMRequest(
        model=model,
        system=[{"type": "text", "text": JUDGE_SYSTEM}],
        messages=[{"role": "user", "content": user}],
        max_tokens=250,
        output_schema=JUDGE_SCHEMA,
        cache=False,
        purpose=f"judge:{item['item_id']}",
        run_id=run_id,
        effort="low" if model.startswith("gpt") else None,
        **kw,
    )


def parse_verdict(text: str) -> str | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0)).get("verdict")
        return v if v in ("pass", "fail") else None
    except json.JSONDecodeError:
        return None


def run_judge(
    items: list[dict],
    results: list[dict],
    run_id: str,
    model: str | None = None,
    links: dict | None = None,
    batch: bool = True,
) -> dict[str, dict]:
    s = get_settings()
    model = model or s.judge_model
    by_id = {r["item_id"]: r for r in results}
    reqs: list[tuple[str, LLMRequest]] = []
    meta: dict[str, str] = {}
    for it in items:
        r = by_id.get(it["item_id"]) or {}
        cls = r.get("classification")
        if not cls or not cls.get("hts10"):
            continue
        ref, src = reference_for(it, links)
        if not ref:
            continue
        meta[it["item_id"]] = src
        reqs.append((it["item_id"], judge_request(it, cls, ref, model, run_id)))
    prov = provider_for(model)
    out: dict[str, dict] = {}
    if batch and hasattr(prov, "complete_batch"):
        res = prov.complete_batch(reqs)
    else:
        from concurrent.futures import ThreadPoolExecutor

        def one(pair):
            iid, req = pair
            try:
                return iid, prov.complete(req)
            except Exception as e:  # noqa: BLE001
                return iid, e

        with ThreadPoolExecutor(max_workers=16) as pool:
            res = dict(pool.map(one, reqs))
    for iid, r in res.items():
        verdict = None if isinstance(r, Exception) else parse_verdict(r.text)
        out[iid] = {
            "verdict": verdict,
            "reference": meta[iid],
            "usd": 0 if isinstance(r, Exception) else r.usd,
        }
    return out
