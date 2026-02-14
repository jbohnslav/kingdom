---
from: claude
to: king
timestamp: 2026-02-14T12:17:16Z
---

Good, the research agent finished. Its findings reinforce the recommendations I laid out above. Let me add a few things the research surfaced that are worth incorporating:

## Additional Insights from the Research

**Aider's three-model split** is directly relevant. Aider has `model` (main chat), `weak-model` (commits/summaries), and `editor-model` (applying edits). Kingdom's analog is: **council agents** (deliberation), **peasant agent** (execution), and **hand agent** (synthesis/design updates). The config should let each role use a different model, which the schema I proposed already supports.

**CrewAI's `role` / `goal` / `backstory` triple** is interesting but too heavy for Kingdom. The per-member `prompt` field in my proposal is the right granularity — it's a single string that shapes the agent's perspective without inventing a new identity language.

**Aider's `extra_params` escape hatch** is worth considering. A catch-all field for passing arbitrary flags to the CLI:

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "cli": "claude --print --output-format json",
      "resume_flag": "--resume",
      "extra_flags": ["--model", "opus-4-6"]
    }
  }
}
```

This avoids having to encode every possible CLI flag as a config key. Users just add what they need.

**Claude Code's layered precedence** (managed > user > project > local) is the right model for Kingdom if/when we add global config. For V1 though, project-level only is fine.

**Cursor's `.mdc` activation modes** are overkill. Kingdom's phases are explicit (`design`, `council`, `peasant`), not inferred. The per-member `prompt` field is sufficient.

## Revised Recommended Schema (V1)

Pulling it all together:

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "cli": "claude --print --output-format json",
      "resume_flag": "--resume",
      "version_command": "claude --version",
      "install_hint": "https://docs.anthropic.com/en/docs/claude-code"
    },
    "codex": {
      "backend": "codex",
      "cli": "codex exec --json",
      "resume_flag": "resume",
      "version_command": "codex --version",
      "install_hint": "npm install -g @openai/codex"
    },
    "kimi": {
      "backend": "cursor",
      "cli": "agent --print --output-format json",
      "resume_flag": "--resume"
    }
  },
  "council": {
    "members": [
      {
        "agent": "claude",
        "prompt": "Focus on architecture, correctness, and edge cases."
      },
      {
        "agent": "codex",
        "prompt": "Search the internet for prior art, existing libraries, and documentation."
      }
    ],
    "timeout": 600
  },
  "peasant": {
    "agent": "kimi",
    "timeout": 900,
    "max_iterations": 50
  }
}
```

## Summary of Key Decisions to Make

| Decision | My Recommendation | Rationale |
|----------|------------------|-----------|
| File format | JSON | Your stated preference; universal familiarity |
| File location | `kingdom.json` at project root | Discoverable; avoids `.kd/` gitignore conflict |
| Agent defs separate from roles | Yes (`agents` + `council.members`) | Avoids duplication when one agent serves multiple roles |
| Per-member prompts | Additive to `COUNCIL_PREAMBLE` | Role-specific instructions without losing safety constraints |
| Peasant agent configurable | Yes, by name reference | Enables cheap-model peasants |
| All optional with defaults | Yes | Zero-config still works; backwards compatible |
| `.kd/agents/*.md` fate | Deprecate in favor of JSON | Two config sources is confusing |
| `kd init` scaffolds config | Yes, with defaults | Makes config discoverable |
| Global config (`~/.config/kingdom/`) | Defer to V2 | Keep scope small |

Want me to write this up into the design doc at `.kd/branches/config-system/design.md`, or do you want to iterate on any of these decisions first?
