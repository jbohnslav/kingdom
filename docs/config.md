# Configuration Reference

Kingdom is configured via `.kd/config.json`. All fields are optional — sensible
defaults are provided for zero-config operation.

## Minimal example

```json
{}
```

This gives you two agents (`claude` and `codex`), both on the council, with
default timeouts. Neither model is pinned: each provider CLI chooses its own
current default.

## Model selection policy

Kingdom keeps its built-in agents unpinned so zero-config projects follow the
provider CLIs and do not break when account access or model catalogs differ.
Set `model` only when a project intentionally needs a stable role or model.
Kingdom records the observed model when the provider exposes it, otherwise the
configured selection or `unknown`. Response frontmatter also records model and
effort source, backend, and the exact CLI version used. `kd doctor` validates
pinned Codex models and effort levels against the account-visible model catalog.

## Full example

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "model": "opus",
      "effort": "high",
      "prompt": "You are a senior Python developer.",
      "prompts": {
        "council": "Focus on architecture.",
        "review": "Be thorough but concise."
      },
      "extra_flags": ["--max-turns", "10"]
    },
    "codex": {
      "backend": "codex",
      "model": "gpt-5.6-sol",
      "effort": "high"
    },
    "codex_peasant": {
      "backend": "codex",
      "model": "gpt-5.6-terra",
      "effort": "medium"
    },
    "claude_lord": {
      "backend": "claude_code",
      "model": "claude-sonnet-5",
      "effort": "high"
    },
    "cursor": {
      "backend": "cursor"
    }
  },
  "prompts": {
    "council": "Default council system prompt for all agents.",
    "design": "Default design phase prompt.",
    "review": "Default review prompt.",
    "peasant": "Default peasant worker prompt."
  },
  "council": {
    "members": ["claude", "codex"],
    "review_members": ["claude", "codex"],
    "timeout": 600,
    "preamble": "You are advising on a Python CLI project.",
    "thinking_visibility": "auto",
    "writable": false,
    "ask": {
      "mode": "broadcast",
      "auto_messages": -1
    },
    "chat": {
      "mode": "natural",
      "auto_rounds": 1
    }
  },
  "peasant": {
    "agent": "codex_peasant",
    "max_iterations": 50
  },
  "lord": {
    "agent": "claude_lord",
    "max_cycles": 200
  }
}
```

Model availability is provider- and account-specific. The example shows a
quality-oriented council/review pair, a balanced worker, and a stronger
supervisor; use unpinned agents when those exact models are unavailable.

## Role-specific agents

Use separate named agents when council, review, peasant, and lord roles need
different cost or capability profiles:

```json
{
  "agents": {
    "claude_council": {
      "backend": "claude_code",
      "model": "opus",
      "effort": "high"
    },
    "codex_council": {
      "backend": "codex",
      "model": "gpt-5.6-sol",
      "effort": "high"
    },
    "codex_peasant": {
      "backend": "codex",
      "model": "gpt-5.6-terra",
      "effort": "medium"
    },
    "claude_lord": {
      "backend": "claude_code",
      "model": "claude-sonnet-5",
      "effort": "high"
    }
  },
  "council": {
    "members": ["claude_council", "codex_council"],
    "review_members": ["claude_council", "codex_council"]
  },
  "peasant": {
    "agent": "codex_peasant"
  },
  "lord": {
    "agent": "claude_lord"
  }
}
```

Use GPT-5.6 Luna for tightly scoped, cost-sensitive workers. Keep `ultra` opt-in:
it enables Codex subagent delegation, which is usually redundant inside
Kingdom's own multi-agent workflows.

## Top-level keys

| Key | Type | Description |
|---|---|---|
| `agents` | object | Agent definitions (keyed by name) |
| `prompts` | object | Default per-phase prompts for all agents |
| `council` | object | Council composition and behavior |
| `peasant` | object | Peasant worker settings |
| `lord` | object | Epic supervisor settings |

No other top-level keys are allowed.

## `agents.<name>`

Each agent is an object with:

| Key | Type | Required | Default | Description |
|---|---|---|---|---|
| `backend` | string | **yes** | — | Agent backend: `claude_code`, `codex`, or `cursor` |
| `model` | string | no | `""` | Model override; empty inherits the provider CLI selection |
| `prompt` | string | no | `""` | System prompt prepended to all queries |
| `prompts` | object | no | `{}` | Per-phase prompt overrides (see below) |
| `extra_flags` | list[string] | no | `[]` | Extra CLI flags passed to the backend |
| `effort` | string | no | `""` | Backend-aware effort override; empty inherits the provider default |

Built-in agents `claude` and `codex` are always present. You can override their
settings or add new agents by name.

Claude supports `low`, `medium`, `high`, `xhigh`, and `max`. Codex additionally
accepts `ultra`; the selected model must support the requested level. Cursor's
CLI does not expose a separate effort flag, so setting `effort` on a Cursor
backend is a validation error. The old Codex-only `reasoning_effort` key remains
accepted as a deprecated alias for `effort`; do not set both.

### `agents.<name>.prompts`

Per-phase prompt overrides for a specific agent. These take priority over the
global `prompts` section.

Valid phases: `council`, `design`, `review`, `peasant`.

## `prompts`

Default prompts applied to all agents when no per-agent override exists.

| Key | Type | Default | Description |
|---|---|---|---|
| `council` | string | `""` | System prompt for council queries |
| `design` | string | `""` | System prompt for design phase |
| `review` | string | `""` | System prompt for code review |
| `peasant` | string | `""` | System prompt for peasant workers |

## `council`

| Key | Type | Default | Description |
|---|---|---|---|
| `members` | list[string] | all agents | Agent names to include in the council |
| `review_members` | list[string] | `members` | Agent names used for automated reviews |
| `timeout` | integer | `600` | Query timeout in seconds (must be > 0) |
| `ask` | object | see below | One-shot council query settings |
| `chat` | object | see below | Interactive council chat settings |
| `preamble` | string | *(none)* | Text prepended to every council query (must be non-empty if specified) |
| `thinking_visibility` | string | `"auto"` | Show reasoning tokens: `auto`, `show`, or `hide` |
| `writable` | boolean | `false` | Allow council members to write files |

Council members must reference agents defined in the `agents` section.

`council.ask` accepts `mode` (`broadcast` or `sequential`) and `auto_messages`
(`-1` = automatic, `0` = disabled, or a positive count). `council.chat`
accepts `mode` (`natural`, `round_robin`, `manual`, or `broadcast`) and a
non-negative `auto_rounds` count.

## `peasant`

| Key | Type | Default | Description |
|---|---|---|---|
| `agent` | string | `"claude"` | Which agent runs peasant tasks |
| `max_iterations` | integer | `50` | Max agent turns per task (must be > 0) |

The peasant agent must reference an agent defined in the `agents` section.

## `lord`

| Key | Type | Default | Description |
|---|---|---|---|
| `agent` | string | peasant agent | Which agent supervises epic execution |
| `max_cycles` | integer | `200` | Maximum supervisor cycles (must be > 0) |

The lord agent must reference an agent defined in the `agents` section. Prefer
a stronger supervisor than the default peasant for multi-ticket epics; mistakes
at this layer affect every delegated task.
