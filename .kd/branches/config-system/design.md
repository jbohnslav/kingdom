# Design: config-system

## Goal

Add a JSON config file that lets users customize agent composition, prompts, and execution settings — without touching code. Zero-config still works with sensible defaults.

## Context

Today, agent definitions live in `.kd/agents/*.md` as YAML frontmatter (name, backend, cli, resume_flag). In practice, nobody has created custom agent files — the directory doesn't even exist in the wild. The defaults are hardcoded in `agent.py:DEFAULT_AGENTS`. Council membership is implicitly "all agents," peasant agent is hardcoded to claude, and there are no per-agent or per-phase prompts.

Users want to:
- Swap council composition (e.g., just Claude + Codex, or five different models via Cursor)
- Give agents specialized prompts (e.g., "search the internet for prior art")
- Set per-phase default prompts (e.g., "prioritize regressions" during review)
- Use cheaper models for peasant work (e.g., Kimi 2.5 instead of Claude)
- Tune timeouts per role

## Requirements

- Single JSON config file at `.kd/config.json`
- Configurable: agent definitions (backend, model, prompt, extra flags), council membership, peasant agent, per-phase prompts (global + per-agent overrides), timeouts
- All fields optional — defaults preserved for zero-config operation
- Dataclasses with manual validation (no pydantic)
- `extra_flags` escape hatch per agent for arbitrary CLI flags
- Prompts are optional, inline strings (not separate files)
- CLI invocation details (how to call each backend, resume flags, output parsing) stay in code — config is for what, code is for how
- CLI flags (e.g., `--timeout`) override config values when provided

## Non-Goals

- TOML or any format other than JSON
- Config layering (global ~/.config/kingdom/, per-user, etc.) — v2
- Profiles/presets — v2
- Budget/cost tracking — v2
- `prompt_file` references to external files — v2 if ever needed
- MCP/tool integration toggles
- Schema version field — add when we actually need to migrate
- Backwards compatibility with `.kd/agents/*.md`

## Config Schema

```json
{
  "agents": {
    "claude": {
      "backend": "claude_code",
      "model": "opus-4-6",
      "prompt": "Focus on architecture, correctness, and edge cases."
    },
    "codex": {
      "backend": "codex",
      "model": "o3",
      "prompt": "Search the internet for prior art and existing libraries."
    },
    "local-llm": {
      "backend": "cursor",
      "model": "llama-3.1-70b",
      "prompts": {
        "peasant": "Follow instructions exactly. Do not improvise. Only change files mentioned in the ticket. Run tests after every change."
      }
    }
  },
  "prompts": {
    "council": "Return analysis and recommendations only. Do not implement.",
    "design": "Focus on design decisions, constraints, and non-goals.",
    "review": "Prioritize regressions, security risks, and missing tests.",
    "peasant": "Follow the ticket instructions precisely. Commit as you go."
  },
  "council": {
    "members": ["claude", "codex"],
    "timeout": 600
  },
  "peasant": {
    "agent": "local-llm",
    "timeout": 900,
    "max_iterations": 50
  }
}
```

### Agent fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `backend` | string | yes | One of: `claude_code`, `codex`, `cursor` |
| `model` | string | no | Model identifier; each backend's command builder knows how to pass it to its CLI |
| `prompt` | string | no | Agent-specific instruction, prepended in all phases |
| `prompts` | dict[str, str] | no | Per-phase prompt overrides (keys: `council`, `design`, `review`, `peasant`). Overrides the global phase prompt for this agent. |
| `extra_flags` | list[str] | no | Additional CLI flags, inserted before the prompt argument |

### Prompts section

Per-phase default prompts that apply to all agents in that phase. Agents can override specific phases via their own `prompts` dict. Agent-level `prompt` is always additive on top.

Safety-critical instructions (e.g., "do not implement") belong in the hardcoded preamble in code, not in configurable prompts — per-agent phase overrides replace the global phase prompt, so anything in the global prompt can be overridden.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `council` | string | (none) | Prepended to all council queries |
| `design` | string | (none) | Prepended during design phase |
| `review` | string | (none) | Prepended during code review |
| `peasant` | string | (none) | Prepended to peasant work prompts |

**Prompt merge order**: safety preamble (hardcoded in code) + phase prompt (agent-specific if set, else global) + agent prompt (config) + user prompt.

### Council fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `members` | list[str] | all defined agents | Agent names to include in council |
| `timeout` | int | 600 | Query timeout (seconds) |

Note: if `council.members` is omitted, all agents defined in `agents` become council members. If you define a peasant-only agent, set `council.members` explicitly to exclude it.

### Peasant fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agent` | string | `"claude"` | Which agent runs peasant work |
| `timeout` | int | 900 | Per-iteration timeout (seconds) |
| `max_iterations` | int | 50 | Max work loop iterations |

## Defaults (no config file)

When `.kd/config.json` doesn't exist, the effective config is:

- **Agents**: claude (claude_code), codex (codex), cursor (cursor) — built-in defaults
- **Council members**: all three
- **Council timeout**: 600s
- **Peasant agent**: claude
- **Peasant timeout**: 900s
- **Peasant max_iterations**: 50
- **Prompts**: none (only hardcoded safety preamble)

## Decisions

- **`.kd/config.json`**: keeps all Kingdom artifacts isolated in `.kd/`. No clutter in the project root. Add `!config.json` to `.kd/.gitignore` to unignore it (since `*.json` is currently ignored).
- **JSON only**: familiar from VS Code, ESLint, tsconfig — everyone knows how to edit it. No TOML.
- **Remove `.kd/agents/*.md` entirely**: single source of truth. No deprecation path — the feature was never used in the wild. Clean break.
- **`model` is first-class**: model is too fundamental to bury in `extra_flags`. Each backend's command builder already knows its CLI's quirks and handles `model` translation internally (e.g., `--model` flag for Claude, different mechanism for Codex). If a backend doesn't support model via CLI, the builder should warn.
- **CLI details stay in code**: `cli`, `resume_flag`, `version_command`, `install_hint` are implementation details of each backend. A `BACKEND_DEFAULTS` dict in code maps backend names to these values. The config says "use codex backend" and the code knows how to invoke codex.
- **`extra_flags` escape hatch**: for anything the config schema doesn't cover — arbitrary CLI flags, no validation on contents. Inserted before the prompt argument in the command. Inspired by Aider's `extra_params`.
- **Per-phase prompts with per-agent overrides**: a top-level `prompts` section sets phase defaults (council, design, review, peasant). Agents can override specific phases via their own `prompts` dict — useful for dumb models that need stricter instructions. Agent-level `prompt` is always additive on top — it's the agent's "personality" that applies in every context.
- **Inline prompts only**: the prompts users will write are short role instructions (1-3 sentences). JSON strings with `\n` work fine. `prompt_file` is a backwards-compatible addition later if needed.
- **Dataclasses with manual validation**: no pydantic. Kingdom is a fast, lightweight tool. Load JSON, validate keys/types by hand, construct dataclasses.
- **Cross-reference validation**: references to undefined agents in `council.members` or `peasant.agent` are hard errors with a clear message listing defined agents.
- **Unknown config keys are hard errors**: catches typos ("timout") immediately. No silent ignoring — fail fast and tell the user exactly which key is unrecognized.
- **CLI flags override config**: `kd council ask --timeout 300` beats `council.timeout` in config, which beats the built-in default.

## Implementation

### New module: `src/kingdom/config.py`

- `KingdomConfig` dataclass (top-level)
- `AgentDef` dataclass (user-facing config: backend, model, prompt, prompts, extra_flags)
- `CouncilConfig`, `PeasantConfig`, `PromptsConfig` dataclasses
- `load_config(base: Path) -> KingdomConfig` — reads `.kd/config.json`, falls back to defaults if file doesn't exist
- `validate_config(data: dict) -> KingdomConfig` — validates types, required fields, cross-references; errors on unknown keys
- Config is loaded once at CLI startup and threaded through

### Backend defaults in code: `BACKEND_DEFAULTS`

A dict in `agent.py` mapping backend name to CLI invocation details:

```python
BACKEND_DEFAULTS = {
    "claude_code": {
        "cli": "claude --print --output-format json",
        "resume_flag": "--resume",
        "version_command": "claude --version",
        "install_hint": "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code",
    },
    "codex": {
        "cli": "codex exec --json",
        "resume_flag": "resume",
        "version_command": "codex --version",
        "install_hint": "Install Codex CLI: npm install -g @openai/codex",
    },
    "cursor": {
        "cli": "agent --print --output-format json",
        "resume_flag": "--resume",
        "version_command": "agent --version",
        "install_hint": "Install Cursor Agent: https://docs.cursor.com/agent",
    },
}
```

Command builders merge `BACKEND_DEFAULTS` with user config at runtime. Each backend's command builder handles `model` translation internally.

### Changes to existing code

- **`agent.py`**: remove `agents_root()`, `parse_agent_file()`, `serialize_agent_file()`, `load_agent()`, `list_agents()`, `create_default_agent_files()`, and `DEFAULT_AGENTS`. Replace with `BACKEND_DEFAULTS` dict. Update `AgentConfig` to a runtime dataclass merging backend defaults + user config. Command builders insert `model` (per-backend logic) and `extra_flags` before the prompt argument.
- **`council/council.py`**: `Council.create()` takes a `KingdomConfig` instead of scanning `.kd/agents/`. Builds members from `config.council.members` list.
- **`council/base.py`**: `CouncilMember.build_command()` prepends phase prompt (if any) + agent prompt (if any) to the council preamble + user prompt.
- **`harness.py`**: read peasant agent from config instead of hardcoding claude. Prepend peasant phase prompt if configured.
- **`design.py`**: derive council member list from config, not hardcoded names.
- **`synthesis.py`**: `COUNCIL_ORDER` derived from config members, not hardcoded `["claude", "codex", "agent"]`.
- **`cli.py`**: load config early, pass to council/peasant creation.
- **`state.py`**: remove auto-creation of empty `config.json` in `ensure_base_layout()`. Config file is created by `kd init` with default content instead.
- **`parsing.py`**: keep as-is — `parse_frontmatter()` is still used by tickets and threads.

### .kd/.gitignore

Add `!config.json` to unignore the config file (since `*.json` is currently ignored).

### kd init

`kd init` scaffolds `.kd/config.json` with the default config (three built-in agents, all on council, claude as peasant). This makes the config discoverable — users see the file and know they can edit it.

### kd config

- `kd config show` — print effective config (defaults + overrides merged)
- No `kd config init` — handled by `kd init`
- `kd doctor` absorbs config validation: parse JSON, check types, verify agent cross-references, check backend CLIs exist via `BACKEND_DEFAULTS[backend]["version_command"]`

### Migration

No migration needed. `.kd/agents/*.md` doesn't exist in any known deployment. Remove all agent file code — no deprecation warnings or fallback logic.

## Council Review (2026-02-14)

Full review thread: `kd council show council-09ef`

### Verdict

All three council members (claude, codex, cursor) agree: implementation faithfully matches the design. 8 of 9 tickets correctly closed. Code is clean and readable. 550 tests pass.

### Bugs Found

1. **`kd doctor` crashes on invalid config** (ticket 3f8e, reopened by codex)
   - `doctor()` calls `get_doctor_checks(base)` even when `check_config()` already detected invalid config. `get_doctor_checks` calls `load_config()` again, which raises `ValueError` → unhandled traceback.
   - Both `kd doctor` and `kd doctor --json` crash. The JSON path is especially bad — outputs traceback instead of valid JSON.
   - Root cause: no guard on `get_doctor_checks()` behind `config_ok`.
   - Existing doctor tests mock `check_config` but don't use real invalid config files, so the bug slipped through.

2. **`kd config show` crashes on invalid config** (same class of bug)
   - Unguarded `load_config()` call without catching `ValueError`.
   - Add to 3f8e scope.

3. **Missing backend validation in `validate_config()`**
   - Unknown backends (e.g., `"foo"`) pass validation silently, crash later in `resolve_agent()`.
   - Should validate backend names against `BACKEND_DEFAULTS` keys at config load time.

4. **Validation accepts non-sensical numeric values**
   - `timeout <= 0` and `max_iterations <= 0` are accepted as valid. Should require positive values.

### Design Gaps (not blocking merge)

- **`design`/`review` prompt fields are no-op at runtime**: schema supports them, but only `council` and `peasant` phase prompts are consumed in code. Acceptable for v1 — the fields are validated and ready for wiring when the design/review flows use them.

### Pre-existing Issues (backlog)

- Variable shadowing in `peasant_start` (`agent` parameter shadowed by loop variable) — not introduced by this branch.

### Action Items

- [x] Fix 3f8e: guard `get_doctor_checks()` and `kd config show` against invalid config
- [x] Add backend validation to `validate_config()`
- [x] Rewrite doctor tests to use `tmp_path` with real invalid config files
- [x] Add positive-value validation for timeouts and max_iterations

### Post-Review Decisions

- **Don't auto-populate models in scaffolded config**: each CLI already knows its own default model. Pinning models in the default config creates maintenance debt — we'd need a PR every time a new model is released. Users add `model` when they want to pin one.
- **Populate repo's `.kd/config.json`**: the empty `{}` was confusing. Now explicitly lists agents, council members, peasant settings — serves as a working example and makes the repo's config discoverable.
- **Removed empty `prompts` from scaffold**: `kd init` no longer writes `"prompts": {}` — less noise, users add prompts when they need them.
