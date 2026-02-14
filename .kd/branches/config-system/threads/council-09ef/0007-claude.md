---
from: claude
to: king
timestamp: 2026-02-14T13:26:01Z
---

OK, I have everything I need. Here's my recommendation.

---

## Recommendation: Single JSON file. Deprecate agents/*.md.

Here's why, and how to handle the multiline prompt problem.

### The multiline problem is smaller than it seems

Look at what the prompts actually are today:

- **Council preamble** (`base.py:39`): 5 lines. This stays in code — it's a safety constraint, not user-configurable.
- **Per-agent council prompt**: Doesn't exist yet. The use case you described is things like *"Search the internet widely for existing docs and repos"* — that's one sentence.
- **Peasant prompt** (`harness.py:36`): 20 lines of structured template. This also stays in code — it's the harness logic, not per-agent customization.

The user-configurable prompts are **role instructions**, not system prompts. They're short. "Focus on architecture and correctness." "Search for prior art." "Be conservative with dependencies." These are 1-3 sentences, not paragraphs.

If someone wants a genuinely long prompt, JSON handles it fine with `\n`:

```json
"prompt": "You are a security-focused reviewer.\nAlways check for OWASP top 10.\nFlag any use of eval() or exec()."
```

Not beautiful, but workable. And for the 95% case, prompts fit on one line.

### What each approach looks like concretely

#### Approach A: Single `kingdom.json` (recommended)

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "cli": "claude --print --output-format json"
    },
    "codex": {
      "backend": "codex",
      "cli": "codex exec --json"
    },
    "kimi": {
      "backend": "cursor",
      "cli": "agent --print --output-format json"
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
        "prompt": "Search the internet for prior art, existing libraries, and relevant documentation. Bring external knowledge into your answer."
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

**Validation**: one `load_config()` function, one schema, one error path. `kd doctor` checks one file.

**Copying between projects**: `cp kingdom.json ../other-project/`

**Discoverability**: `kd init` creates it with commented defaults (or prints "created kingdom.json with default config").

#### Approach B: JSON + agents/*.md for prompts

```
kingdom.json:
```
```json
{
  "council": {
    "members": [
      {"agent": "claude"},
      {"agent": "codex"}
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

```
.kd/agents/claude.md:
```
```markdown
---
name: claude
backend: claude_code
cli: claude --print --output-format json
---

Focus on architecture, correctness, and edge cases.
Consider failure modes and error handling.
```

```
.kd/agents/codex.md:
```
```markdown
---
name: codex
backend: codex
cli: codex exec --json
---

Search the internet for prior art, existing libraries,
and relevant documentation. Bring external knowledge
into your answer.
```

**Problems with this approach:**

1. **Two sources of truth**: `kingdom.json` says who's on the council, `agents/*.md` says what they are. If someone adds a member to `kingdom.json` but forgets the `.md` file, what happens? If someone edits the `.md` file for an agent not in the council, is that an error?

2. **Copying between projects** now requires copying `kingdom.json` AND `.kd/agents/`. Users will forget.

3. **Validation splits**: `load_config()` must read JSON, then walk the filesystem for `.md` files, then cross-reference. Two error paths.

4. **The gitignore problem**: `.kd/*.json` is gitignored. You'd have to either put `kingdom.json` at root (mixing config locations) or fix the gitignore (which risks exposing `state.json`).

#### Approach C: JSON with `prompt_file` reference (compromise — not recommended)

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "cli": "claude --print --output-format json",
      "prompt": "Focus on architecture and correctness."
    },
    "security-reviewer": {
      "backend": "claude_code",
      "cli": "claude --print --output-format json",
      "prompt_file": "prompts/security-review.md"
    }
  }
}
```

This is clever but adds complexity for a case that barely exists. You now have two ways to specify a prompt, two code paths, and a file-resolution question (relative to what?). If someone actually needs a 50-line prompt, they can use `\n` in JSON or we can add this later.

### Why A wins

| Concern | A (single JSON) | B (JSON + agents/*.md) |
|---------|-----------------|----------------------|
| Single source of truth | Yes | No — split across formats |
| Copy between projects | `cp kingdom.json` | `cp kingdom.json` + `cp -r .kd/agents/` |
| Validation | One file, one pass | Cross-reference two sources |
| Long prompts | `\n` in strings (fine for 1-5 lines) | Markdown body (nicer for 10+ lines) |
| Discoverability | One file to find and read | Two places to look |
| `kd doctor` | Check one file | Check file + directory + cross-references |
| Git tracking | Root-level, always tracked | Needs gitignore fix |

The **only** advantage of B is nicer multiline editing. But the prompts users will write are short role instructions, not essays. And if someone truly needs long prompts, you can add `prompt_file` as a V2 feature — it's backwards-compatible.

### Migration path for agents/*.md

Since no `.kd/agents/` files exist in the wild yet (the directory isn't even created in this repo), there's nothing to migrate. The `DEFAULT_AGENTS` in code become the defaults when `kingdom.json` doesn't exist. Clean break.

The `agents_root()`, `parse_agent_file()`, `list_agents()`, and `serialize_agent_file()` functions in `agent.py` can be removed (or kept as fallback during a deprecation period if you prefer caution).

### One more thing: `kd config` subcommand

Consider adding:

```
kd config init          # scaffold kingdom.json with defaults
kd config show          # print effective config (defaults + overrides)
kd config check         # validate kingdom.json, check agent CLIs exist
```

`kd config show` is especially valuable — it shows what the system will actually use, resolving defaults and overrides. OpenClaw has `/context list` for this; Claude Code doesn't, and people constantly wonder "which settings are active?"
