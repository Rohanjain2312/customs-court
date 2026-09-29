"""Load and validate an Agent Skill (SKILL.md with YAML front matter)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tariffagent.config import ROOT

SKILL_DIR = ROOT / "skills" / "gri-classification"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    meta: dict

    def reference(self, name: str) -> str:
        return (self.path / "references" / name).read_text()


def _parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML front matter")
    end = text.index("\n---\n", 4)
    fm, body = text[4:end], text[end + 5 :]
    meta: dict = {}
    current = None
    for line in fm.splitlines():
        if not line.strip():
            continue
        if line.startswith("  ") and current:
            k, _, v = line.strip().partition(":")
            meta.setdefault(current, {})[k.strip()] = v.strip().strip('"')
            continue
        k, _, v = line.partition(":")
        current = k.strip()
        meta[current] = v.strip() if v.strip() else {}
    return meta, body.lstrip()


def load_skill(path: Path = SKILL_DIR) -> Skill:
    meta, body = _parse_front_matter((path / "SKILL.md").read_text())
    errors = validate(meta, path)
    if errors:
        raise ValueError("; ".join(errors))
    return Skill(name=meta["name"], description=meta["description"], body=body, path=path, meta=meta)


def validate(meta: dict, path: Path) -> list[str]:
    """Checks from the Agent Skills specification (agentskills.io/specification)."""
    errs = []
    name = meta.get("name", "")
    if not name or len(name) > 64 or not NAME_RE.match(name):
        errs.append("name must be 1-64 chars of lowercase letters, digits and single hyphens")
    if name != path.name:
        errs.append(f"name {name!r} must match the directory name {path.name!r}")
    desc = meta.get("description", "")
    if not desc or len(desc) > 1024:
        errs.append("description must be 1-1024 characters")
    comp = meta.get("compatibility")
    if isinstance(comp, str) and len(comp) > 500:
        errs.append("compatibility must be at most 500 characters")
    for ref in re.findall(r"references/[\w.-]+\.md", (path / "SKILL.md").read_text()):
        if not (path / ref).exists():
            errs.append(f"missing referenced file {ref}")
    return errs
