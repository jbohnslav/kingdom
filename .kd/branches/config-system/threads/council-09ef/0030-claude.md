---
from: claude
to: king
timestamp: 2026-02-14T17:40:55Z
---

---

## Council Review: config-system Branch

### Design Alignment: Excellent

The implementation faithfully follows the design doc. Every major decision has been carried through:

- **Single JSON config at `.kd/config.json`** — done
- **5 dataclasses** (`AgentDef`, `PromptsConfig`, `CouncilConfig`, `PeasantConfig`, `KingdomConfig`) — all present, correct fields
- **`BACKEND_DEFAULTS` in code** — replaces `DEFAULT_AGENTS`, maps backend names to CLI invocation details exactly as designed
- **Prompt merge order** (safety preamble + phase prompt + agent prompt + user prompt) — correctly implemented in `CouncilMember.build_command()` at `base.py:58-64`
- **Agent-specific phase prompts override global** — implemented in `council.py:44` and `harness.py:269`
- **CLI flags override config** — `council_ask` correctly uses `Optional[int]` for `--timeout` and only overrides when explicitly provided
- **Unknown keys are hard errors** — `check_unknown_keys()` covers all sections
- **Cross-reference validation** — council members and peasant agent validated against defined agents
- **`kd init` scaffolds config** — idempotent, doesn't overwrite existing
- **`.kd/.gitignore` has `!config.json`** — confirmed in both the template and the live file
- **Old agent file code fully removed** — zero references to `agents_root`, `parse_agent_file`, etc. in the codebase
- **`kd config show`** — works, outputs valid JSON with merged effective config
- **`kd doctor` validates config** — partially working (see bugs below)

### Ticket Status

| Ticket | Status | Verdict |
|--------|--------|---------|
| e01c | closed | Correctly closed — timeout fix verified |
| 3860 | closed | Correctly closed — parent/umbrella ticket |
| d52d | closed | Correctly closed — config.py is solid |
| a9f1 | closed | Correctly closed — init + gitignore working |
| fe0b | closed | Correctly closed — harness/design/synthesis wired |
| 5151 | closed | Correctly closed — agent.py fully refactored |
| b65d | closed | Correctly closed — council wiring + prompt merging |
| fc3f | closed | Correctly closed — `kd config show` works |
| **3f8e** | **open** | **Correctly open — bug confirmed and reproduced** |

### Test Suite

**550 passed, 3 skipped.** Clean.

### Bugs Found

#### 1. Ticket 3f8e — `kd doctor` crashes on invalid config (CONFIRMED)

The worklog on the ticket already identifies this precisely. When config is invalid:
- `check_config()` correctly returns `(False, error_message)`
- Doctor prints the error
- But then `get_doctor_checks(base)` at `cli.py:2040` calls `load_config(base)` **again**, which raises `ValueError` and produces an unhandled traceback

Both `kd doctor` and `kd doctor --json` crash. The JSON path is especially bad — it outputs a traceback instead of valid JSON.

**Root cause:** `doctor()` doesn't guard `get_doctor_checks()` behind `config_ok`. When config is bad, it should either skip CLI checks entirely or fall back to default agents for CLI checking.

**Additional variant:** An unknown backend (e.g., `{"agents":{"test":{"backend":"foo"}}}`) passes `validate_config()` but crashes in `get_doctor_checks()` → `resolve_all_agents()` → `resolve_agent()`. This is because `validate_config` doesn't validate backend names.

#### 2. `kd config show` crashes on invalid config (NEW — related to 3f8e)

`kd config show` calls `load_config(base)` without catching `ValueError`, so invalid config produces a raw traceback instead of a friendly error. This is the same class of bug — unguarded `load_config` calls in CLI commands.

**Recommendation:** Add to ticket 3f8e's scope, or create a separate ticket. The fix pattern is the same: catch `ValueError` from `load_config()` and display a clean error.

#### 3. Missing backend validation in `validate_config` (DESIGN GAP)

The design says backend should be `"One of: claude_code, codex, cursor"` but `validate_agent()` only checks it's a non-empty string. An unknown backend silently passes config validation and only crashes later when `resolve_agent()` tries to look it up in `BACKEND_DEFAULTS`.

**Recommendation:** Add backend validation to `validate_agent()` in `config.py`. This follows the design's "fail fast" principle. Could import `BACKEND_DEFAULTS` from `agent.py` or define a `VALID_BACKENDS` set in `config.py`.

### Doctor Test Coverage Gap

The existing doctor tests (`test_doctor_invalid_config`, `test_doctor_json_invalid_config`) patch `check_config` to return an error but don't prevent `get_doctor_checks(base)` from calling the real `load_config`. They pass only because they run in the project directory where `config.json` is `{}` (valid). These tests don't actually catch the bug they claim to test. When the ticket is fixed, these tests should be rewritten to use `tmp_path` with an actually-invalid config file.

### Code Quality Assessment

**Strengths:**
- Clean, readable code throughout. The config validation is thorough and produces excellent error messages with precise context (`"agents.{name}.prompts.{phase} must be a string"`)
- Good separation of concerns: config.py for schema/validation, agent.py for runtime merge + command building
- `BACKEND_DEFAULTS` is a clean replacement for the never-used agent file system
- Prompt merge order is clear and well-commented
- 550 tests — comprehensive coverage
- The `default_config()` pattern is elegant — zero-config works perfectly

**Minor observations (not blockers):**
- `kd config show` outputs empty strings (`"model": ""`, `"prompt": ""`) and empty collections (`"prompts": {}`, `"extra_flags": []`) for all default fields. This is technically correct ("effective config") but noisy for discovery. A `--compact` flag or omitting empty defaults could help — but this is polish for later.
- `peasant_start` at `cli.py:1154` shadows the `agent` parameter with a loop variable `for agent in list_active_agents(...)`. This is a pre-existing bug on master, not introduced by this branch. Worth a backlog ticket.
- The repo's actual `.kd/config.json` is `{}`. After `kd init` scaffolds defaults, the team might want to update the repo's config to match.

### Recommendations

1. **Fix ticket 3f8e** — guard `get_doctor_checks()` behind `config_ok` in `doctor()`. When config is bad, skip CLI checks (or use defaults). Same pattern needed for JSON output path.
2. **Fix `kd config show` crash** — catch `ValueError` from `load_config()`, display clean error. Add to 3f8e or create a sibling ticket.
3. **Add backend validation** to `validate_config()` — fail early on unknown backends instead of crashing later in `resolve_agent()`. Consider this for 3f8e scope since it directly impacts doctor.
4. **Rewrite doctor tests** to use `tmp_path` with actually-invalid config files instead of mocking `check_config`.
5. **Backlog:** file a ticket for the `agent` variable shadowing in `peasant_start` (pre-existing, not branch-related).

### Bottom Line

This is a well-executed feature branch. The design is faithfully implemented, the code is clean, and 8 of 9 tickets are correctly closed. The one remaining ticket (3f8e) is correctly open with a clear root cause identified. The bugs are all in the same category — unguarded `load_config()` calls in CLI commands — and the fix is straightforward. Once 3f8e is resolved (with the `config show` and backend validation additions), this branch is ready for PR.
