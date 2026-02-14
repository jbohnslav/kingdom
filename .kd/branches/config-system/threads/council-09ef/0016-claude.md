---
from: claude
to: king
timestamp: 2026-02-14T14:07:39Z
---

OK. I have the full picture. Here's my review.

---

## Second Review: config-system design doc

The doc has improved significantly. The decisions are clearer, the `BACKEND_DEFAULTS` structure is explicit, and the previous gaps (design.py, cross-reference validation, unknown keys) are addressed. Here's what remains.

### Issue 1: `.kd/config.json` is gitignored

This is a showstopper. The `.kd/.gitignore` at line 2 says `*.json`. That means `.kd/config.json` won't be tracked by git. The whole point of config is that it's shared with the team and version-controlled.

Three fixes, pick one:
- **(a)** Add `!config.json` to `.kd/.gitignore` — negate the pattern for this specific file
- **(b)** Move config to `kingdom.json` at project root (where it was before)
- **(c)** Change `.kd/.gitignore` to be more specific — ignore `state.json`, `*.jsonl`, `*.log` etc. instead of blanket `*.json`

I'd go with (a) — it's one line, targeted, and doesn't require rethinking the gitignore or the file location. Add it to the design doc so the implementer doesn't discover this at the end.

### Issue 2: `model` translation per-backend is unspecified

The design says `model` is first-class and "code translates to the right CLI flag per backend." Good decision. But the doc doesn't show *how*. Looking at the current command builders, none of them handle a model parameter. The implementation will need to add model injection to each builder:

- `build_claude_command`: insert `--model opus-4-6`
- `build_codex_command`: insert `--model o3` (or `-m o3`? need to check `codex exec --help`)
- `build_cursor_command`: insert `--model llama-3.1-70b` (or is it set at the Cursor IDE level, not CLI?)

This is straightforward for Claude and Codex, but Cursor Agent's model selection might not be a CLI flag at all — it might be determined by the IDE configuration or `.cursor/rules`. If that's the case, `model` would silently do nothing for cursor-backend agents.

**Recommendation**: Add a brief note in the `BACKEND_DEFAULTS` section specifying how each backend translates `model`. Something like:

```python
BACKEND_DEFAULTS = {
    "claude_code": {
        "model_flag": "--model",  # claude --model opus-4-6
        ...
    },
    "codex": {
        "model_flag": "--model",  # codex exec --model o3
        ...
    },
    "cursor": {
        "model_flag": "--model",  # or None if cursor doesn't support it
        ...
    },
}
```

If a backend doesn't support `model` via CLI, the command builder should warn (not silently ignore), since the user clearly expects model selection to work.

### Issue 3: Prompt merge order needs a concrete example

The merge order is stated abstractly:

> safety preamble (hardcoded in code) + phase prompt (agent-specific if set, else global) + agent prompt (config) + user prompt

But consider this config:

```json
{
  "agents": {
    "claude": {
      "prompt": "Focus on architecture.",
      "prompts": { "council": "Be extra thorough." }
    }
  },
  "prompts": {
    "council": "Return analysis only."
  }
}
```

When claude gets a council query "How should we design auth?", the final prompt is:

```
[safety preamble: "You are a council advisor..."]
[phase prompt: "Be extra thorough."  ← agent-specific overrides global "Return analysis only."]
[agent prompt: "Focus on architecture."]
[user prompt: "How should we design auth?"]
```

Is that right? The global phase prompt `"Return analysis only."` is *replaced*, not merged. The doc says "Overrides the global phase prompt for this agent" (line 87), which is clear. But the example shows the global prompt has safety-relevant content ("Return analysis only. Do not implement.") — if the agent override forgets to include that, you lose the constraint.

This might be fine — the hardcoded safety preamble already says "do not implement" — but it's worth being aware that per-agent phase overrides can accidentally weaken global instructions. The design should note that safety-critical instructions belong in the hardcoded preamble, not in configurable prompts.

### Issue 4: `council_ask` has a `--timeout` CLI flag — how does it interact with config?

`cli.py:302`: `timeout: Annotated[int, typer.Option("--timeout", ...)] = 600`

Today the user can do `kd council ask --timeout 300 "question"`. The design doesn't address whether CLI flags override config. Presumably they should (CLI > config > defaults), but this needs to be stated.

**Recommendation**: Add one line to the Decisions or Implementation section: "CLI flags (e.g., `--timeout`, `--agent`) override config values when provided."

### Issue 5: `state.py` creates an empty `.kd/config.json` on init

`state.py:228-230`:
```python
config_path = state_root(base) / "config.json"
if not config_path.exists():
    write_json(config_path, {})
```

The design says to "remove any `.kd/config.json` references" from `state.py`. But now config *is* at `.kd/config.json`. So should `ensure_base_layout()` still create an empty one? Or should it stop creating it (and `load_config` handles the missing-file case by returning defaults)?

I'd say: stop creating the empty file in `ensure_base_layout()`. Let `load_config()` return defaults when the file doesn't exist. Reserve `kd config init` for explicit scaffolding. An empty `{}` file is confusing — it looks like something's broken, and the user has to know to add content.

**Recommendation**: Update the `state.py` bullet: instead of "remove references," say "remove the auto-creation of empty `config.json` in `ensure_base_layout()`. Config file is created explicitly by `kd config init`."

### Issue 6: Missing — what are the defaults when config doesn't exist?

The design says "falls back to defaults" but never spells them out as a complete example. When there's no `kingdom.json` or `.kd/config.json`, what's the effective config?

This matters because `Council.create()` currently creates all three default agents (claude, codex, cursor). If config doesn't exist and the default is "no agents defined," that's a regression. If the default is "all three built-in agents," that needs to be explicit.

**Recommendation**: Add a "Defaults" subsection showing the effective config when no file exists:

```
Agents: claude (claude_code), codex (codex), cursor (cursor) — from BACKEND_DEFAULTS
Council members: all three
Council timeout: 600s
Peasant agent: claude
Peasant timeout: 900s
Peasant max_iterations: 50
Prompts: none (only hardcoded safety preamble)
```

### Issue 7: Minor — `parsing.py` removal claim is wrong

The design says "remove `parse_frontmatter()` if no longer used elsewhere." But `parse_frontmatter` is used by `thread.py:300` and `ticket.py:113`. It's only removed from `agent.py`. Don't touch `parsing.py`.

### Summary

| Issue | Severity | Action |
|-------|----------|--------|
| `.kd/config.json` is gitignored by `*.json` | **High** | Add `!config.json` to `.kd/.gitignore` |
| `model` flag translation unspecified | Medium | Add `model_flag` to `BACKEND_DEFAULTS` |
| CLI `--timeout` vs config precedence | Medium | State "CLI flags override config" |
| `state.py` auto-creates empty config | Low | Stop auto-creating; let `kd config init` handle it |
| No explicit defaults section | Low | Add effective defaults when no config exists |
| `parse_frontmatter` still used elsewhere | Low | Remove the `parsing.py` bullet |
| Phase override can weaken global prompts | Low | Note: safety constraints go in hardcoded preamble |

With issue 1 fixed and the other medium items addressed, this is ready to implement.
