"""Structured outputs shared by every agent arm."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class CitedRuling(BaseModel):
    id: str
    status: Literal["in_force", "modified", "revoked", "unknown"]


class RejectedAlternative(BaseModel):
    code: str
    reason: str


class Facts(BaseModel):
    material: str = ""
    function: str = ""
    form: str = ""
    end_use: str = ""


class Classification(BaseModel):
    hts10: str = Field(description="10-digit HTS code formatted NNNN.NN.NN.NN, or empty when abstaining")
    facts: Facts = Facts()
    gri_path: list[str] = Field(description="GRI steps applied in order, one short line each")
    deciding_gri: str = Field(
        description="The GRI that decided the heading, for example 'GRI 1' or 'GRI 3(b)'"
    )
    cited_rulings: list[CitedRuling]
    rejected_alternatives: list[RejectedAlternative]
    missing_facts: list[str]
    confidence: float = Field(description="0 to 1")
    abstain: bool
    rationale: str = Field(description="Two to five sentences of legal reasoning")

    @property
    def digits(self) -> str:
        return re.sub(r"\D", "", self.hts10 or "")


def strict_schema(model: type[BaseModel]) -> dict:
    """JSON schema accepted by structured outputs: inline refs, no extra keys, all required."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def fix(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return fix(defs[node["$ref"].split("/")[-1]])
            out = {}
            for k, v in node.items():
                if k in ("title", "default", "minimum", "maximum"):
                    continue
                out[k] = fix(v)
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"].keys())
            return out
        if isinstance(node, list):
            return [fix(x) for x in node]
        return node

    return fix(raw)


CLASSIFICATION_SCHEMA = strict_schema(Classification)


class AdvocateMemo(BaseModel):
    heading: str = Field(description="4-digit heading argued for")
    best_code: str = Field(description="Best 10-digit code under this heading")
    argument: str
    supporting_rulings: list[CitedRuling]
    exclusions_against: list[str] = Field(description="Notes or exclusions that hurt this heading")
    strength: float = Field(description="0 to 1, honest strength of the case")


ADVOCATE_SCHEMA = strict_schema(AdvocateMemo)


class Plan(BaseModel):
    facts: Facts
    missing_facts: list[str]
    candidate_headings: list[str] = Field(description="2 to 4 plausible 4-digit headings")
    reasoning: str


PLAN_SCHEMA = strict_schema(Plan)
