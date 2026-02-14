---
from: claude
to: king
timestamp: 2026-02-14T05:29:40Z
---

Good, it handles missing directories. Now I have everything I need for a thorough review.

---

## Code Review: ready-tickets-batch

### c5cb — Replace `kd breakdown` with agent prompt output

**Acceptance criteria:** Met. The old parsing/creation logic is fully gutted, replaced with a printed prompt instructing agents to use `kd tk create` and `kd tk dep`.

**Code quality:** Clean. Net deletion of ~200 lines of fragile markdown parsing. The replacement is a simple string builder — minimal and readable. `build_breakdown_template`, `read_breakdown`, `write_breakdown`, and `ensure_breakdown_initialized` correctly retained.

**Issues:**
- None significant. The test update in `test_cli_design_breakdown.py` correctly checks the new output rather than the old file content.

**Verdict: Pass**

---

### 8af5 — `kd done` should error if open tickets

**Acceptance criteria:** All 4 checked. Error lists tickets, suggests next steps, `--force` bypasses.

**Code quality:** Clean, minimal insertion at the right point.

**Issues:**
- The ticket check runs even for legacy `.kd/runs/` paths (line 242: `tickets_dir = source_dir / "tickets"`). If a legacy branch has no `tickets/` directory, `list_tickets()` returns `[]` (safe), so no bug — but the check is a no-op on legacy branches. Acceptable since legacy is being phased out.

**Verdict: Pass**

---

### 101d — Council read-only enforcement

**Acceptance criteria:** 2 of 3 checked in the ticket; the 3rd ("test that a council query doesn't produce file modifications") is noted as deferred for manual testing. That's reasonable — it needs a live agent.

**Code quality:** Good two-layer defense. The preamble is explicit and specific. The `--allowedTools` restriction for Claude is correct — no Bash, Edit, Write. Codex sandbox and Cursor `--mode ask` are appropriate.

**Issues:**
- The Claude `--allowedTools` list does not include `Bash`. This is intentional and correct for read-only, but it means council members **cannot run `kd design show`** as instructed in the preamble (line 45: "run `kd design show` to print it"). The preamble tells them to run a CLI command, but they have no `Bash` tool to do it. They'd need to `Read` the design.md file directly instead. **Consider updating the preamble to say "read the design.md file directly" rather than "run `kd design show`".**
- The `WebFetch` and `WebSearch` tools in the allowlist are fine but worth noting — council members can make external web requests. This seems intentional for research.

**Verdict: Pass with one nit** (preamble instruction contradicts tool restrictions)

---

### 98fe — `kd start` initializes design doc

**Acceptance criteria:** All 3 met. `start()` calls `ensure_design_initialized`, prints the path, and `kd design` remains idempotent.

**Code quality:** Minimal — 4 lines added. Uses the existing `ensure_design_initialized` function exactly as intended.

**Issues:**
- None.

**Verdict: Pass**

---

### 98f3 — `kd tk move` cross-filesystem fix

**Acceptance criteria:** No explicit criteria listed in the ticket (bug report), but the described behavior (source copy left behind) is fixed.

**Code quality:** Good. The `try/except OSError` around `Path.rename()` with `shutil.copy2` + `unlink` fallback is the correct pattern. Tests cover both the cross-filesystem case (via monkeypatched `rename`) and the duplicate destination case.

**Issues:**
- **Atomicity gap in the fallback path:** If `shutil.copy2` succeeds but `ticket_path.unlink()` fails (e.g., permission error), the ticket is duplicated — the exact bug this was supposed to fix. This is unlikely in practice but worth noting. A mitigation would be to wrap the copy+unlink in a try/except that cleans up `new_path` if `unlink` fails. Low risk though.
- The test in `test_cli_ticket.py` (line 758-759) asserts the source is removed after a CLI `move` — good regression coverage.

**Verdict: Pass with minor note** (unlink failure leaves duplicate, but extremely unlikely)

---

### e4b1 — `kd status` with agent assignments

**Acceptance criteria:** No explicit criteria in ticket, but described goals are met: shows assignments grouped by assignee, includes role/agent_name in JSON output.

**Code quality:** Mostly clean, but has a real bug.

**Issues:**

**BUG: `kd status --json` outputs JSON twice.** Lines 1863-1864 and 1882-1883:

```python
if output_json:                          # line 1863
    typer.echo(json.dumps(output, indent=2))  # FIRST print (incomplete — no role/assignments)
# ... compute role, assignments, add to output ...
if output_json:                          # line 1882
    typer.echo(json.dumps(output, indent=2))  # SECOND print (complete)
```

The first `if output_json` block at line 1863 dumps the `output` dict *before* role, agent_name, and assignments are added. Then the second block at line 1882 dumps the complete dict. So `kd status --json` prints two JSON objects to stdout — the first incomplete, the second complete. Any JSON parser consuming this output will break.

**Fix:** Remove the first `if output_json: typer.echo(...)` block (lines 1863-1864). The second one at 1882 already handles JSON output with the complete data.

Additionally:
- `import os` at line 1866 is redundant — `os` is already imported at the top of the file (line 11). Harmless but messy.
- The role detection logic is duplicated between `status()` and `whoami()`. A shared helper would be cleaner, but this is a style nit, not a bug.

**Verdict: FAIL — must fix the double JSON output bug**

---

### 2819 — `kd whoami` command

**Acceptance criteria:** No explicit criteria in ticket, but described goals are met: command exists, uses env vars, council/harness inject role info.

**Code quality:** Clean. The `clean_agent_env()` extension is backward-compatible (optional params default to None). Council and harness spawn sites correctly inject role/agent_name.

**Issues:**
- The "hand" detection via `CLAUDECODE` env var is clever — `clean_agent_env()` strips `CLAUDECODE`, so child processes won't falsely detect it. Good design.
- No tests for the `whoami` command itself. The env var injection into `clean_agent_env` is tested indirectly through the agent tests. A quick CLI test for `whoami` (with/without env vars) would be good to add, but not blocking.

**Verdict: Pass**

---

## Summary

| Ticket | Verdict | Notes |
|--------|---------|-------|
| c5cb | **Pass** | Clean deletion, minimal replacement |
| 8af5 | **Pass** | Correct guard with --force escape hatch |
| 101d | **Pass (nit)** | Preamble says "run `kd design show`" but Bash tool is blocked |
| 98fe | **Pass** | Minimal, uses existing helper |
| 98f3 | **Pass (minor)** | Tiny atomicity gap in fallback, very low risk |
| e4b1 | **Fail** | `kd status --json` emits two JSON objects — first incomplete, second complete |
| 2819 | **Pass** | No whoami-specific tests, but acceptable |

### Must fix before merge:
1. **e4b1 double JSON output** — remove the first `if output_json: typer.echo(...)` block at `cli.py:1863-1864`. The assignment computation and second JSON dump at line 1882 should be the only output path.

### Should fix (non-blocking):
2. **101d preamble contradiction** — change "run `kd design show`" to "read the design.md file directly" in `COUNCIL_PREAMBLE`, since council members have no Bash tool.
3. **e4b1 redundant import** — remove `import os` at line 1866 (already imported at top of file).
