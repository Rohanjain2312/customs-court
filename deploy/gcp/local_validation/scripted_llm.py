"""Scripted ADK models for local validation only. Not shipped to Agent Runtime.

Each ScriptedLlm plays one role (orchestrator, advocate, adjudicator) with a fixed tool
plan and reads codes and ruling ids out of the real MCP tool results. The answers are
not model output; they prove the wiring: ADK agent tree, state hand-off between agents,
McpToolset over streamable HTTP against the local MCP container.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import ClassVar

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

CODE = re.compile(r'\\?"code\\?":\s*\\?"([\d.]+)\\?"')
HTS10 = re.compile(r"\b(\d{4}\.\d{2}\.\d{2}\.\d{2})\b")
RULING = re.compile(r'\\?"id\\?":\s*\\?"([A-Z]{1,2}\d{5,6})\\?"')
STATUS = re.compile(r'\\?"status\\?":\s*\\?"(in_force|modified|revoked|unknown)\\?"')


def _all_text(req: LlmRequest) -> str:
    out = []
    si = req.config.system_instruction if req.config else None
    if isinstance(si, str):
        out.append(si)
    elif si is not None:
        out.extend(p.text or "" for p in (getattr(si, "parts", None) or []))
    for c in req.contents or []:
        out.extend(p.text or "" for p in (c.parts or []) if p.text)
    return "\n".join(out)


def _responses(req: LlmRequest) -> list[tuple[str, str]]:
    out = []
    for c in req.contents or []:
        for p in c.parts or []:
            if p.function_response:
                out.append((p.function_response.name, json.dumps(p.function_response.response)))
    return out


def _call(name: str, args: dict) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _reply(parts: list[types.Part]) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=parts))


def _text(obj: dict) -> LlmResponse:
    return _reply([types.Part(text=json.dumps(obj))])


class ScriptedLlm(BaseLlm):
    role: str = "orchestrator"
    calls: ClassVar[list[dict]] = []  # every request seen, for the validation checks

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        text = _all_text(llm_request)
        resp = _responses(llm_request)
        ScriptedLlm.calls.append(
            {"role": self.role, "tools": sorted(llm_request.tools_dict or {}), "responses": len(resp)}
        )
        product = re.search(r"<product_description>\s*(.*?)\s*</product_description>", text, re.S)
        product = product.group(1) if product else ""
        yield getattr(self, f"_{self.role}")(text, product, resp)

    def _orchestrator(self, text: str, product: str, resp) -> LlmResponse:
        done = {n for n, _ in resp}
        if "hts_search" not in done:
            return _reply([_call("hts_search", {"text": product[:120], "limit": 8})])
        body = dict(resp)["hts_search"]
        heads = []
        for code in CODE.findall(body):
            h = re.sub(r"\D", "", code)[:4]
            if len(h) == 4 and h not in heads:
                heads.append(h)
        return _text(
            {
                "facts": {"material": "", "function": "", "form": "", "end_use": ""},
                "missing_facts": [],
                "candidate_headings": heads[:2],
                "reasoning": "scripted local validation, not model output",
            }
        )

    def _advocate(self, text: str, product: str, resp) -> LlmResponse:
        m = re.search(r"Heading under review: (\d{4})", text)
        heading = m.group(1) if m else ""
        done = dict(resp)
        if not resp:
            return _reply(
                [
                    _call("get_notes", {"scope": "chapter", "id": heading[:2]}),
                    _call("hts_navigate", {"code": heading}),
                    _call("cross_search", {"query": product[:120], "limit": 3}),
                ]
            )
        rid = RULING.search(done.get("cross_search", ""))
        if rid and "ruling_status" not in done:
            return _reply([_call("ruling_status", {"id": rid.group(1)})])
        codes = [c for c in CODE.findall(done.get("hts_navigate", "")) if c.startswith(heading[:4])]
        st = STATUS.search(done.get("ruling_status", ""))
        return _text(
            {
                "heading": heading,
                "best_code": codes[-1] if codes else heading,
                "argument": "scripted local validation, not model output",
                "supporting_rulings": [{"id": rid.group(1), "status": st.group(1) if st else "unknown"}]
                if rid
                else [],
                "exclusions_against": [],
                "strength": 0.5,
            }
        )

    def _adjudicator(self, text: str, product: str, resp) -> LlmResponse:
        memos = re.search(r"<advocate_memos>(.*?)</advocate_memos>", text, re.S)
        memos = json.loads(memos.group(1)) if memos else []
        navs = [body for n, body in resp if n == "hts_navigate"]
        found = HTS10.findall(navs[-1]) if navs else []
        if not found and len(navs) < 4:
            if navs:
                last = navs[-1]
                cur = re.search(r'\\?"node\\?":\s*\{\\?"code\\?":\s*\\?"([\d.]+)', last)
                cur_digits = len(re.sub(r"\D", "", cur.group(1))) if cur else 0
                deeper = [c for c in CODE.findall(last) if len(re.sub(r"\D", "", c)) > cur_digits]
                target = deeper[0] if deeper else None
            else:
                target = memos[0]["best_code"] if memos else None
            if target:
                return _reply([_call("hts_navigate", {"code": target})])
        cited = [r for m in memos for r in m.get("supporting_rulings", [])][:2]
        return _text(
            {
                "hts10": found[0] if found else "",
                "facts": {"material": "", "function": "", "form": "", "end_use": ""},
                "gri_path": ["GRI 1: scripted local validation answer, not model output"],
                "deciding_gri": "GRI 1",
                "cited_rulings": cited,
                "rejected_alternatives": [
                    {"code": m["heading"], "reason": "scripted"} for m in memos[1:] if m.get("heading")
                ],
                "missing_facts": [],
                "confidence": 0.0,
                "abstain": not found,
                "rationale": "Scripted reply used to validate the ADK package wiring. Not a classification.",
            }
        )


def scripted_models() -> dict:
    ScriptedLlm.calls.clear()
    return {
        "orchestrator": ScriptedLlm(model="scripted-orchestrator", role="orchestrator"),
        "advocate": ScriptedLlm(model="scripted-advocate", role="advocate"),
        "adjudicator": ScriptedLlm(model="scripted-adjudicator", role="adjudicator"),
    }
