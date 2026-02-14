---
from: claude
to: king
timestamp: 2026-02-14T13:32:57Z
---

Good, now I have the full picture. Here's my review.

---

## Design Review: config-system

Overall this is solid. The scope is right, the decisions are well-reasoned, the schema is clean. Here are the issues I found, in order of severity.

### 1. `model` field is redundant with `extra_flags` — and the doc doesn't say how it works

The schema has both:
```json
"model": "opus-4-6",
"extra_flags": ["--model", "opus-4-6"]
```

The example literally shows the same value in both places. But the design never explains how `model` gets turned into a CLI flag. Each backend passes model differently:
- Claude: `--model opus-4-6`
- Codex: `--model o3` (or env var `OPENAI_MODEL`)
- Cursor: `--model` flag, or it's set in the Cursor IDE settings

So the code would need per-backend logic to translate `"model": "X"` into the right flag. That's exactly the kind of "CLI invocation detail" the design says should stay in code, not config.

**Recommendation**: Drop `model` from the schema. Users who want to set a model use `extra_flags: ["--model", "opus-4-6"]`. This is what the escape hatch is for. It's explicit, backend-agnostic, and doesn't require Kingdom to know how each CLI handles model selection. If you later find that 90% of users are writing `"extra_flags": ["--model", "X"]`, you can add a `model` convenience field then — it's backwards-compatible.

### 2. `extra_flags` injection point is unspecified

The design says flags are "appended to commands." But the current command builders have very specific flag ordering:

- `build_claude_command`: inserts `--dangerously-skip-permissions` at position 1, puts `-p PROMPT` at the end
- `build_codex_command`: inserts permission flag at position 1, appends prompt at the very end
- `build_cursor_command`: inserts `--force --sandbox disabled` at positions 1-3, appends prompt, then resume flag

If extra flags are appended after the prompt, some CLIs might interpret them as part of the prompt text. If they're inserted before the prompt, they might conflict with positional flags.

**Recommendation**: State explicitly in the design: "extra_flags are inserted before the prompt argument." And add a note that the command builders need to handle this carefully — the prompt should always be the last (or near-last) argument.

### 3. `AgentConfig` name collision

The design says to create a new `AgentConfig` in `config.py` that "replaces current one in `agent.py`." But the current `AgentConfig` is used in:
- `agent.py` (definition + command builders + response parsers)
- `council/base.py` (CouncilMember holds a reference)
- `council/council.py` (creates CouncilMembers from configs)
- `harness.py` (loads config for peasant work)

The new config `AgentConfig` drops `cli` and `resume_flag`. But `build_claude_command` at `agent.py:266` does `shlex.split(config.cli)`. The command builders *need* a `cli` string — it's just going to come from the backend defaults in code instead of from config.

**Recommendation**: The design should clarify that there are two layers: (1) the config-level `AgentConfig` (what the user specifies: backend, prompt, extra_flags), and (2) the runtime `AgentConfig` that the command builders consume (which merges config + backend defaults like cli string and resume_flag). Call them different things — maybe `AgentDef` for the config layer, `AgentConfig` for the runtime layer, or just document the merge step explicitly. This is the trickiest part of the implementation and the design hand-waves it.

### 4. Hardcoded agent names in `design.py` and `synthesis.py`

`synthesis.py:7`: `COUNCIL_ORDER = ["claude", "codex", "agent"]`
`design.py:137`: `for name in ["claude", "codex", "agent"]:`

The design mentions fixing `synthesis.py` but doesn't mention `design.py`. Both iterate over council members by hardcoded name. Both need to derive the list from config.

**Recommendation**: Add `design.py` to the "Changes to existing code" section. Both `build_synthesis_prompt` and `build_design_update_prompt` need to iterate over `config.council.members` instead of hardcoded lists.

### 5. The `timeout` precedence is ambiguous

Timeout can be set in three places:
- Per-agent: `agents.claude.timeout`
- Council-wide: `council.timeout`
- Peasant-wide: `peasant.timeout`

What wins? If `agents.claude.timeout = 300` and `council.timeout = 600`, and claude is a council member, which timeout applies?

**Recommendation**: Pick one rule and document it. My suggestion: per-agent timeout overrides role timeout. So `agents.claude.timeout` beats `council.timeout` when claude is queried as a council member. This lets you give a slow agent more time without affecting the others. If this feels over-designed for V1, drop per-agent timeout entirely — just have `council.timeout` and `peasant.timeout`.

### 6. Missing: what happens when `council.members` references a nonexistent agent?

```json
{
  "agents": { "claude": { ... } },
  "council": { "members": ["claude", "typo-agent"] }
}
```

The design says "validate types, required fields, unknown keys (warn and ignore)" but doesn't cover cross-reference validation. This will be a common user error.

**Recommendation**: Add to the validation section: "References to undefined agents in `council.members` or `peasant.agent` are hard errors." Print a clear message: `Error: council member "typo-agent" not found in agents. Defined agents: claude, codex`.

### 7. Missing: `kd doctor` integration details

The design says `kd doctor` absorbs config validation, but doesn't say what it checks. Today `kd doctor` presumably checks if CLIs are installed.

**Recommendation**: Spell out what `kd doctor` checks post-config:
- `kingdom.json` parses as valid JSON
- All required fields present, correct types
- All agent references resolve
- Backend CLIs are installed (via `version_command` — but wait, that's being dropped from config... how does doctor know what to run?)

This reveals another gap: if `cli` and `version_command` move to code-level backend defaults, the code needs a `BACKEND_DEFAULTS` dict that maps `"claude_code"` to `{"cli": "claude --print ...", "version_command": "claude --version", "install_hint": "..."}`. The design should mention this structure.

### 8. Minor: council `members` default is "all agents"

The design says if `council.members` is omitted, the default is "all agents." But "all agents" means all agents defined in `kingdom.json`, or all default agents? If someone defines `agents: {claude: ..., kimi: ...}` for the purpose of having claude on council and kimi as peasant, but omits `council.members`, suddenly kimi is on the council too.

**Recommendation**: Make the default more explicit. Either: (a) default is the three built-in agents (claude, codex, cursor), or (b) default is all defined agents. If (b), document the gotcha: "If you define a peasant-only agent, explicitly set `council.members` to exclude it."

I'd lean toward (b) with the documentation, since it's the simpler rule.

### 9. Minor: open question answer

The design asks: "Should unknown keys in `kingdom.json` warn or silently ignore?"

**Recommendation**: Warn on stderr but don't error. Print something like `Warning: unknown key "agents.claude.foobar" in kingdom.json (ignored)`. This catches typos (`"timout"` instead of `"timeout"`) without breaking forward compatibility when a newer version of Kingdom adds fields that an older version doesn't know about.

### Summary

| Issue | Severity | Recommendation |
|-------|----------|---------------|
| `model` redundant with `extra_flags` | Medium | Drop `model`, use `extra_flags` |
| `extra_flags` injection point | Medium | Specify "before prompt argument" |
| `AgentConfig` name collision / merge step | Medium | Document the two-layer model explicitly |
| Hardcoded names in `design.py` | Low | Add to changes list |
| Timeout precedence | Low | Drop per-agent timeout for V1, or specify precedence |
| Missing cross-reference validation | Low | Agent refs are hard errors |
| `kd doctor` / `BACKEND_DEFAULTS` gap | Low | Add backend defaults dict to design |
| Council members default gotcha | Low | Document the "all agents" behavior |
| Unknown keys | Low | Warn on stderr, don't error |
