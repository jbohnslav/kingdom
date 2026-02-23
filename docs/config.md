# Configuration Reference

Kingdom is configured via `.kd/config.json`. All fields are optional — sensible
defaults are provided for zero-config operation.

## Minimal example

```json
{}
```

This gives you two agents (`claude` and `codex`), both on the council, with
default timeouts.

## Full example

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "model": "opus",
      "prompt": "You are a senior Python developer.",
      "prompts": {
        "council": "Focus on architecture.",
        "review": "Be thorough but concise."
      },
      "extra_flags": ["--max-turns", "10"]
    },
    "codex": {
      "backend": "codex",
      "model": "o3"
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
    "timeout": 600,
    "auto_messages": -1,
    "mode": "broadcast",
    "preamble": "You are advising on a Python CLI project.",
    "thinking_visibility": "auto",
    "writable": false
  },
  "peasant": {
    "agent": "claude",
    "timeout": 900,
    "max_iterations": 50
  }
}
```

## Top-level keys

| Key | Type | Description |
|---|---|---|
| `agents` | object | Agent definitions (keyed by name) |
| `prompts` | object | Default per-phase prompts for all agents |
| `council` | object | Council composition and behavior |
| `peasant` | object | Peasant worker settings |

No other top-level keys are allowed.

## `agents.<name>`

Each agent is an object with:

| Key | Type | Required | Default | Description |
|---|---|---|---|---|
| `backend` | string | **yes** | — | Agent backend: `claude_code`, `codex`, or `cursor` |
| `model` | string | no | `""` | Model override (e.g. `"opus"`, `"o3"`) |
| `prompt` | string | no | `""` | System prompt prepended to all queries |
| `prompts` | object | no | `{}` | Per-phase prompt overrides (see below) |
| `extra_flags` | list[string] | no | `[]` | Extra CLI flags passed to the backend |

Built-in agents `claude` and `codex` are always present. You can override their
settings or add new agents by name.

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
| `timeout` | integer | `600` | Query timeout in seconds (must be > 0) |
| `auto_messages` | integer | `-1` | Auto-turn follow-up messages: `-1` = auto, `0` = disabled, `N` = exactly N |
| `mode` | string | `"broadcast"` | Query mode: `broadcast` (parallel) or `sequential` |
| `preamble` | string | *(none)* | Text prepended to every council query (must be non-empty if specified) |
| `thinking_visibility` | string | `"auto"` | Show reasoning tokens: `auto`, `show`, or `hide` |
| `writable` | boolean | `false` | Allow council members to write files |

Council members must reference agents defined in the `agents` section.

## `peasant`

| Key | Type | Default | Description |
|---|---|---|---|
| `agent` | string | `"claude"` | Which agent runs peasant tasks |
| `timeout` | integer | `900` | Task timeout in seconds (must be > 0) |
| `max_iterations` | integer | `50` | Max agent turns per task (must be > 0) |

The peasant agent must reference an agent defined in the `agents` section.
