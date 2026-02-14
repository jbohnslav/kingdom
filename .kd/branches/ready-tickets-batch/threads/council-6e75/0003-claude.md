---
from: claude
to: king
timestamp: 2026-02-14T04:42:38Z
---

Now I have a thorough understanding of all 9 tickets and the codebase. Here's my analysis:

---

## Ticket Implementation Guidance

### Priority 1

#### **c5cb** — Replace `kd breakdown` with agent prompt output
**Files to touch:** `src/kingdom/cli.py` (breakdown command ~L829-907), `src/kingdom/breakdown.py`
**Approach:** Gut the current `breakdown()` command body. Remove the `--apply` flag, `parse_breakdown_tickets()` call, the two-pass create+link algorithm, and the state.json mapping logic. Replace with a function that reads `design.md`, builds a prompt instructing an agent to use `kd tk create` and `kd tk dep` CLI commands, and prints it to stdout. In `breakdown.py`, delete `parse_breakdown_tickets()` and any related helpers. Remove tests for the deleted parsing logic.
**Gotchas:**
- The `build_breakdown_template()` function may still be useful for the prompt — evaluate before deleting
- Check if anything else imports `parse_breakdown_tickets` (grep for it)
- The state.json `breakdown_id -> ticket_id` mapping can be removed if nothing reads it downstream
- Don't break `design_show()` or `design_approve()` which share the `get_branch_paths()` helper

---

#### **8af5** — `kd done` should error if branch has open tickets
**Files to touch:** `src/kingdom/cli.py` (done command ~L203-269), `src/kingdom/ticket.py` (for `list_tickets`)
**Approach:** After resolving the branch directory in `done()`, call `list_tickets()` on the branch's tickets dir. Filter for status != "closed". If any remain and `--force` is not set, print each open ticket (ID + title + status) and exit with a non-zero code via `raise typer.Exit(1)`. Add a `force: bool = typer.Option(False, "--force")` parameter. Error message should suggest: "Close tickets, move them to backlog with `kd tk move`, or use `--force`."
**Gotchas:**
- The current `done()` signature takes only `feature`. Adding `--force` is clean since typer handles it
- Make sure to handle the legacy `.kd/runs/` path too, or decide to skip it (it's backwards compat code)
- Ticket status values to check: `open` and `in_progress` (both are "not done")

---

### Priority 2

#### **98f3** — `kd tk move` should remove ticket from source location *(BUG FIX)*
**Files to touch:** `src/kingdom/ticket.py` (`move_ticket` ~L362-383)
**Approach:** Actually... looking at the code, `move_ticket()` already uses `Path.rename()` which is an atomic move — it removes the source. The bug described says "the source copy is left behind." This suggests the issue might be in the CLI layer (`ticket_move` in cli.py ~L2473-2538) where `find_ticket()` might be finding a backlog copy and the branch copy, or the move is using `shutil.copy` somewhere instead of rename. **Investigate carefully before changing anything.** The rename approach should work on the same filesystem, but cross-filesystem moves (e.g., if worktrees are on different mounts) would silently copy instead.
**Gotchas:**
- If the ticket is found via `find_ticket()` which searches multiple locations, the "source" might not be what you expect
- Cross-filesystem `Path.rename()` raises `OSError` — may need `shutil.move()` as a fallback
- Need to verify: is the bug that `find_ticket` returns the backlog match, copies to branch, but backlog copy persists? Or is it a different flow?

---

#### **98fe** — `kd start` should initialize design doc
**Files to touch:** `src/kingdom/cli.py` (start command ~L151-201), `src/kingdom/design.py` (`ensure_design_initialized`)
**Approach:** After `ensure_branch_layout()` in `start()`, call `ensure_design_initialized(design_path, feature)` and then print the design path. `ensure_design_initialized` already exists and does exactly the right thing — creates the template if missing, no-ops if present. Just need to compute `design_path` from the branch layout and wire it in. Also print the path so the user knows where to edit.
**Gotchas:**
- `ensure_branch_layout()` already creates the directory structure, so the design.md parent dir will exist
- The `design_default()` command should remain working (it already calls `ensure_design_initialized` — just verify idempotency)
- Use the original (non-normalized) branch name as the `feature` arg to `build_design_template` for readability

---

#### **101d** — Council members should not modify files (enforce read-only)
**Files to touch:** `src/kingdom/council/base.py` (COUNCIL_PREAMBLE ~L39-45), `src/kingdom/agent.py` (command builders ~L257-317), possibly `.kd/agents/*.md` default configs
**Approach:** Two layers of defense:
1. **Prompt layer:** Strengthen `COUNCIL_PREAMBLE` to explicitly forbid writes, edits, deletions, and any file modifications. Be specific: "Do NOT create, edit, delete, or write any files. Do NOT run git commands that modify state. You are read-only."
2. **Tool/permission layer:** For Claude Code, add `--allowedTools` flag to restrict to read-only tools (Read, Glob, Grep, WebFetch, WebSearch — no Bash, Edit, Write). For Codex, use `--sandbox read-only` if available. For Cursor, check `--sandbox` options.
**Gotchas:**
- `build_claude_command()` currently uses `--dangerously-skip-permissions` which gives full access — this is the opposite of what you want for council. You'll need to replace this with explicit tool allowlists for council queries vs. peasant work
- The `skip_permissions` parameter in `build_command()` is currently always True for council — need to differentiate council (read-only) from peasant (full access) invocations
- Codex and Cursor may have different sandboxing mechanisms — check their CLI docs

---

#### **3860** — Add JSON config file for system-wide settings
**Files to touch:** New logic in `src/kingdom/config.py` (or extend existing), `src/kingdom/agent.py`, `src/kingdom/council/council.py`, `src/kingdom/cli.py`
**Approach:** Create a `kingdom.toml` or `kingdom.json` at project root (or `.kd/config.json` which already exists). Define schema covering: council members (name, backend, model), per-agent permissions, per-phase prompt overrides (ask, design, review). Load it early in CLI startup. Have agent loading fall back to config file values when `.kd/agents/*.md` files don't exist. Gradually migrate hardcoded defaults to config.
**Gotchas:**
- `.kd/config.json` already exists — check what's in it and whether to extend it vs. create a new top-level file
- This is the most invasive ticket — it touches the loading path for agents, council, and prompts
- Consider making this additive (config file optional, defaults preserved) to avoid breaking existing setups
- TOML is more human-friendly than JSON for a config file users will edit

---

#### **b5aa** — Enable branch protection on master
**Files to touch:** None in the codebase — this is a GitHub admin action
**Approach:** Use `gh api` to set branch protection rules on master. Require PRs, require approvals, block direct pushes.
**Gotchas:**
- This is an ops task, not a code change — no PR needed
- Requires admin permissions on the GitHub repo
- After enabling, all agents (including peasants with `--dangerously-skip-permissions`) will be blocked from direct pushes, which is the goal
- Consider: do you want required status checks too? (CI passing before merge)

---

#### **e4b1** — Add `kd status` command for agent workload *(depends on 2819)*
**Files to touch:** `src/kingdom/cli.py` (extend existing `status` command ~L1811-1900 or add a new subcommand), `src/kingdom/session.py`, `src/kingdom/ticket.py`
**Approach:** Extend the existing `status` command (or add `kd status --agents` / `kd agent status`). Query `whoami` to get current role, then: list tickets assigned to current agent (filter `list_tickets()` by assignee field), show their status and paths. For the dashboard view, iterate all session files in `sessions/` and all tickets, group by assignee.
**Gotchas:**
- Depends on **2819** (`kd whoami`) for the "who am I" resolution — must be implemented after
- The `assignee` field on tickets already exists in the data model, and `kd tk assign/unassign` commands exist
- The existing `status` command shows branch-level info — be careful not to break its current output
- Consider: should this be a flag on `status` or a separate subcommand?

---

### Priority 3

#### **2819** — Add `kd whoami` command
**Files to touch:** `src/kingdom/cli.py` (new command), `src/kingdom/session.py` (for state lookup)
**Approach:** Add a `whoami()` command to the CLI. Detection logic:
1. Check environment variables (e.g., `KD_ROLE`, `KD_AGENT_NAME`) — peasants/council could set these when spawned
2. Check session state — if there's an active session with a matching PID
3. Check if running inside a worktree (peasant indicator)
4. Fall back to "king" (interactive user)

Print the role and agent name if applicable.
**Gotchas:**
- For this to be useful, the council worker and harness need to *set* the identifying env vars when spawning agents — that's additional plumbing
- Without env vars, detection is best-effort (PID matching is fragile)
- Consider: should `whoami` also work from the SKILL.md prompt context (i.e., the skill tells the agent its role)?

---

## Dependency Graph & Ordering

```
Independent (can parallelize):
  c5cb (breakdown rewrite)
  8af5 (done + open ticket check)
  98f3 (move bug fix)
  98fe (start + design init)
  101d (council read-only)
  b5aa (GitHub branch protection)
  3860 (config file)

Sequential chain:
  2819 (whoami) → e4b1 (status/workload)
```

## Recommended Execution Order

**Group 1 — Quick wins (small, isolated):**
1. **98f3** (bug fix, ~5 lines changed)
2. **98fe** (start + design, ~10 lines added)
3. **8af5** (done + force flag, ~20 lines added)

**Group 2 — Medium effort, isolated:**
4. **c5cb** (breakdown rewrite — net deletion of code, satisfying)
5. **101d** (council read-only — prompt + command builder changes)
6. **b5aa** (GitHub admin — zero code, just `gh api` calls)

**Group 3 — Larger / dependencies:**
7. **2819** (whoami — new command + env var plumbing)
8. **e4b1** (status dashboard — depends on 2819)
9. **3860** (config file — most invasive, touches many modules)

## Conflicts & Concerns

- **c5cb vs 3860**: The config file ticket wants per-phase prompt overrides. If breakdown is gutted first, the config file won't need a breakdown prompt section — do c5cb first.
- **101d vs 3860**: The config file could be where per-agent permissions live. If 3860 goes first, 101d can use it. If 101d goes first, it'll hardcode the restrictions and 3860 can later externalize them. Either order works but doing 101d first is safer (immediate security fix).
- **101d vs agent.py changes**: The `--dangerously-skip-permissions` flag is used for both council (should be read-only) and peasants (need write access). 101d must split this code path — be careful not to break peasant functionality.
- **No missing dependencies detected** — the declared `deps: [2819]` on e4b1 is correct and sufficient.
