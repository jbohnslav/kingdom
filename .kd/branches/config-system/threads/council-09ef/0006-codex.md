---
from: codex
to: king
timestamp: 2026-02-14T13:25:46Z
---

I’ll stay in advisory mode and evaluate the tradeoff directly against the current architecture, then I’ll give a concrete recommendation with JSON examples for both single-file and dual-source designs.
Skill used: `kingdom` (this is a `kd` workflow/config architecture decision).

**Recommendation**
Deprecate `.kd/agents/*.md` as a config source and make `.kd/config.json` the single source of truth.
Keep long prompts as optional external files referenced from JSON (for example `.kd/prompts/*.md`), but do not treat those files as agent config.

This gives you one place to validate, copy, diff, and reason about behavior, while still solving multiline prompt ergonomics.

**Why**
- Single-source config avoids drift and precedence bugs.
- Manual dataclass validation is much simpler with one canonical JSON schema.
- Portability improves: copy one JSON file across repos/teams.
- Current `.kd/agents/*.md` parsing is frontmatter-only today (`src/kingdom/agent.py`, `src/kingdom/parsing.py`), so keeping it as a second source adds complexity fast.

**Approach A (recommended): single JSON source + optional prompt file refs**
```json
{
  "version": 1,
  "roles": {
    "council": { "members": ["codex_research", "claude_arch"] },
    "peasant": { "default_agent": "kimi_worker" }
  },
  "agents": {
    "codex_research": {
      "backend": "codex",
      "model": "gpt-5.3-codex",
      "timeout_seconds": 600,
      "system_prompt_file": ".kd/prompts/codex_research.md",
      "extra_flags": ["--search"],
      "extra_params": { "reasoning_effort": "high" }
    },
    "claude_arch": {
      "backend": "claude_code",
      "model": "claude-opus-4.1",
      "timeout_seconds": 600,
      "system_prompt": "Focus on architecture risks and tradeoffs.",
      "extra_flags": [],
      "extra_params": {}
    },
    "kimi_worker": {
      "backend": "cursor",
      "model": "kimi-2.5",
      "timeout_seconds": 900
    }
  }
}
```

Example prompt file:
```md
# .kd/prompts/codex_research.md
Search broadly for similar repos/docs. Cite concrete links and call out proven patterns.
```

**Approach B (alternative): JSON + `.kd/agents/*.md` for prompts**
```json
{
  "version": 1,
  "roles": {
    "council": { "members": ["codex_research", "claude_arch"] },
    "peasant": { "default_agent": "kimi_worker" }
  },
  "agents": {
    "codex_research": {
      "backend": "codex",
      "model": "gpt-5.3-codex",
      "timeout_seconds": 600,
      "prompt_ref": ".kd/agents/codex_research.md",
      "extra_flags": ["--search"],
      "extra_params": { "reasoning_effort": "high" }
    }
  }
}
```

```md
---
name: codex_research
---
Search broadly for similar repos/docs. Cite concrete links and call out proven patterns.
```

Tradeoff: this works, but you now have two “config-ish” sources and cross-file validation/preference rules.

**If you choose the recommended path**
- Treat `.kd/agents/*.md` as legacy input only during migration.
- End state: JSON authoritative; prompt files are content assets, not config sources.
- Validation rule: allow exactly one of `system_prompt` or `system_prompt_file` per agent.
