# Architecture

(Components, data flow, sequence and cloud diagrams are completed in Phase 6.)

## Agent Skill: `gri-classification`

Location: `skills/gri-classification/`

```
SKILL.md                               front matter + broker workflow (2,459 tokens)
references/examples.md                 9 worked examples from real CROSS rulings
references/gri-3b-composites-and-sets.md
references/parts-and-accessories.md
references/ruling-status.md
scripts/validate_hts.py                format and existence check (local DB or USITC API)
```

### What we borrowed

From the Agent Skills specification (agentskills.io/specification, read 2026-09-28):
- Front matter with `name` (lowercase, hyphens, matches the directory) and a `description` that says what the skill does and when to use it, with trigger keywords. Optional `license`, `compatibility` and `metadata` fields.
- Progressive disclosure: short metadata, a body under 5,000 tokens (ours is 2,459), detail pushed into `references/`, code in `scripts/`.
- File references one level deep from `SKILL.md`.
- Scripts that are self-contained, give helpful errors and handle edge cases (`validate_hts.py` uses only the standard library and returns exit code 2 when it cannot check).

From anthropics/skills (the `mcp-builder` skill in particular, read 2026-09-28):
- A numbered workflow with named phases, and references loaded only when a case needs them.
- Naming the exact tools the skill expects, so the skill and the MCP server work as one unit. Every step in our workflow names its MCP tool.

`src/tariffagent/agents/skill.py` loads the skill and checks the specification rules (name format and match, description length, compatibility length, referenced files exist). `tests/test_agent_e2e.py::test_skill_loads_and_is_valid` runs those checks.

### How the agent uses it

The skill body is part of the cached static prefix of every agent call (system prompt, skill body, GRI text). The worked examples were chosen from rulings dated before 2026-07-01 and outside every evaluation set, and none shares an 8-digit code with an ATLAS test or validation gold code, so the references cannot leak answers.
