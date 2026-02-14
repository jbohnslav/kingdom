# Design: Backlog Cleanup — Batch Fix Workflow Issues

## Goal

Resolve 11 open backlog tickets in one coordinated pass. Fix council UX bugs, streamline ticket workflow, improve the branch lifecycle, and harden infra. After this branch, the day-to-day `kd` experience should feel noticeably smoother.

## Context

Kingdom's core workflow (`kd start` → design → breakdown → work → done) works but has accumulated friction:

- **Council is fragile:** async-by-default was a workaround for Claude Code's bash timeout (should just set `BASH_DEFAULT_TIMEOUT_MS`), and there's no quick way to @mention members inline.
- **Tickets are clunky:** `kin-` prefix is redundant noise, no assignment tracking, batch operations require repeated commands.
- **Lifecycle has rough edges:** `kd done` creates uncommitted archive changes after PR merge, design docs have no approved state.
- **No branch protection** on master — agents with `--dangerously-skip-permissions` can push directly.

## Council Review Findings

Several tickets are **already implemented** and just need verification + closure:

- **kin-c749** (council watch --to mismatch): `ask_expected` is already passed to `watch_thread` at cli.py:438-439. Tests pass. **Close after verification.**
- **kin-d5ae** (auto-pull backlog tickets): `_resolve_peasant_context(auto_pull=True)` already handles this at cli.py:1015. `TestBacklogAutoPull` passes. **Close after verification.**
- **kin-8393** (multi-ID tk pull): `tk pull` already accepts multiple IDs with 2-pass validation at cli.py:2321. `TestTicketPull` passes. **Close after verification.** However, `tk move` still only accepts a single ID (see below).

Key risks identified:
- Ticket ID migration is under-scoped — hardcoded `kin-` in frontmatter IDs, deps, parent refs all need rewriting, not just filenames
- `tk move` variadic IDs conflicts with current positional `[target]` arg — needs CLI redesign
- Design doc approved state is a schema shift (state.json → frontmatter), not trivial

## Tickets (grouped by theme)

### Theme 1: Council UX (4 tickets)

| ID | P | Title | Status |
|----|---|-------|--------|
| kin-c749 | P1 | Council watch vs --to mismatch | **Already fixed** — verify & close |
| kin-db3b | P2 | Revert council async default, use BASH_DEFAULT_TIMEOUT_MS | Needs work |
| kin-b43e | P2 | Council timeout too short, needs better debug output | Needs work |
| kin-09c9 | P2 | @ mentions to tag council members inline | Needs work |

**kin-c749 (verify & close):** The ask command already computes `ask_expected = {to} if to else {m.name for m in c.members}` and passes it to `watch_thread`. Tests confirm. However, standalone `kd council watch` (without an ask) still falls back to thread members, which can mismatch on targeted follow-ups in mixed-member threads. This is an edge case worth noting but not blocking.

**kin-db3b:** Revert async-by-default from kin-7bd5. Make `council ask` synchronous again (dispatch + watch inline). Add `BASH_DEFAULT_TIMEOUT_MS=300000` to CLAUDE.md so Claude Code doesn't kill long-running council queries. Keep `--async` as opt-in.

**kin-b43e:** Default council timeout is already 300s, so no increase needed. The real fix is `BASH_DEFAULT_TIMEOUT_MS` in CLAUDE.md (from kin-db3b). Add a progress line during watch showing elapsed time and which members have responded so the user knows it's working. Consider a simple `[elapsed] Waiting for: claude, codex...` line that updates.

**kin-09c9:** Parse `@member` mentions from the prompt string in `council ask`. Extract mentioned names, validate against known members, and use them as the `--to` target list. Multiple mentions → query only those members. `@all` supported as explicit "query everyone" override. Parser must avoid false positives on `@` in code blocks or email addresses — only match `@word` tokens at word boundaries against known member names. Fail loudly on unknown `@mentions`.

### Theme 2: Ticket Workflow (4 tickets)

| ID | P | Title | Status |
|----|---|-------|--------|
| kin-98e7 | P2 | Simplify ticket IDs — drop kin- prefix or use integers | Needs work (high blast radius) |
| kin-b76b | P2 | Assign tickets to agents and show current assignment | Needs work |
| kin-d5ae | P2 | Auto-pull backlog tickets when starting work | **Already fixed** — verify & close |
| kin-8393 | P3 | Support multiple ticket IDs in tk pull/move | **tk pull done**, tk move needs redesign |

**kin-98e7 (high blast radius — isolate):** Drop the `kin-` prefix from ticket IDs. This is more than a display change:
- **File renames:** `kin-a321.md` → `a321.md` (use `git mv` to preserve history)
- **Frontmatter rewrite:** `id: kin-a321` → `id: a321` in every ticket file
- **Dep/parent refs:** `deps: [kin-c3d4]` → `deps: [c3d4]` across all tickets
- **Code changes:** `generate_ticket_id` drops the prefix, `find_ticket` updated, any hardcoded `kin-` references in cli.py/ticket.py
- **Migration:** Explicit `kd migrate ticket-ids` command with `--dry-run` / `--apply` flags. No silent auto-migration — user must opt in. Scans backlog, all branches, and archive.

**kin-b76b:** Add `assignee` field to ticket frontmatter (dataclass field already exists). New commands:
- `kd tk assign <id> <agent>` — sets assignee
- `kd tk unassign <id>` — clears assignee
- `kd tk show` with no args — shows ticket assigned to "hand" (current agent)
- `kd tk list` — shows assignee column
- `kd peasant start` — auto-sets assignee to the peasant session name

**kin-d5ae (verify & close):** `_resolve_peasant_context(auto_pull=True)` already moves backlog tickets into the branch ticket directory. `TestBacklogAutoPull` passes. Verify end-to-end and close.

**kin-8393 (partial — tk pull done, tk move needs work):** `tk pull` already accepts variadic `ticket_ids`. For `tk move`, the current signature `tk move <ticket_id> [target]` conflicts with variadic IDs. Redesign: `kd tk move <ids>... --to <target>` (target becomes a required `--to` flag when moving multiple). Single-ID move without `--to` can keep current behavior for backwards compat.

### Theme 3: Lifecycle (2 tickets)

| ID | P | Title | Status |
|----|---|-------|--------|
| kin-a321 | P2 | kd done timing creates awkward git workflow | Needs work |
| kin-b504 | P3 | Design doc approved state | Needs work |

**kin-a321:** `kd done` becomes a status transition, not a filesystem operation. Remove the `shutil.move` to archive. Instead: set `status: "done"` + `done_at` in state.json, clear session pointer, remove worktrees. No tracked files change. All CLI commands that iterate branches must filter out done branches by default (`kd status`, `kd tk list`, `kd tk ready`, `kd start` suggestions, `kd tk pull` source search). Add `--all` / `--include-done` flags where users need to see archived work. The `.kd/archive/` directory becomes unnecessary — existing archives can stay but no new ones are created.

**kin-b504:** Design doc approved state. Currently `state.json` has a `design_approved` boolean and `kd design approve` already exists (sets it in state.json). This is a schema decision:
- **Option A:** Keep using state.json (already works, `kd status` just needs to read it)
- **Option B:** Add frontmatter to design.md (more visible, but design.md currently has no frontmatter)

Recommendation: stick with state.json since `kd design approve` already writes to it. Just wire `kd status` to display it. Smaller change, no schema migration.

### Theme 4: Infrastructure (1 ticket)

| ID | P | Title | Status |
|----|---|-------|--------|
| kin-b5aa | P2 | Enable branch protection on master | Needs work |

**kin-b5aa:** Use `gh api` to set branch protection rules on master: require PR, require 1 approval, block direct pushes. One-time command, not a code change. Do this early to protect master while we work on everything else.

## Requirements

- All 11 tickets resolved and closed
- No regressions in existing workflow — run full test suite after each theme
- Ticket ID migration handles frontmatter IDs, deps, parent refs, and filenames
- Migration uses `git mv` to preserve file history
- Council sync behavior restored with proper timeout configuration
- CLAUDE.md updated with `BASH_DEFAULT_TIMEOUT_MS=300000`
- `kd done` produces zero tracked file changes — status-only transition
- All CLI commands filter out done branches by default

## Non-Goals

- Agent skills spec (kin-cf85) — separate effort
- Major council architecture changes (e.g., replacing subprocess dispatch)
- New UI framework or output formatting overhaul
- `kd gc` or periodic cleanup of done branches (future if clutter becomes an issue)

## Execution Order (revised per council feedback)

### Phase 1: Verify & close already-done tickets
1. **kin-c749** — verify council watch targeting works, close
2. **kin-d5ae** — verify auto-pull works end-to-end, close
3. **kin-8393** — verify multi-ID tk pull works, update ticket scope to tk move only

### Phase 2: Infrastructure
4. **kin-b5aa** — enable branch protection on master (protect early)

### Phase 3: Council fixes (ship together)
5. **kin-db3b** — revert async default, add BASH_DEFAULT_TIMEOUT_MS to CLAUDE.md
6. **kin-b43e** — add progress indicator to watch, confirm timeout is adequate
7. **kin-09c9** — @mentions parsing with `@all` support

### Phase 4: Ticket workflow
8. **kin-b76b** — assignee tracking (assign/unassign/show/list)
9. **kin-8393** (remaining) — tk move `--to` flag redesign for multi-ID support

### Phase 5: Lifecycle
10. **kin-a321** — kd done status-only (remove archive move, filter done branches in all commands)
11. **kin-b504** — wire `kd status` to show design_approved from state.json

### Phase 6: Migration (isolated, high blast radius)
12. **kin-98e7** — ticket ID simplification with explicit `kd migrate ticket-ids --dry-run/--apply`

## Decisions

- **Drop `kin-` prefix entirely:** IDs become bare 4-char hex. Migration via explicit `kd migrate ticket-ids` command with `--dry-run` preview. Rewrites filenames, frontmatter IDs, deps, and parent refs. Uses `git mv` for history.
- **`kd done` is status-only, no file moves:** Archive is a state (`status: "done"` in state.json), not a directory. No tracked files change. CLI commands filter done branches by default. Eliminates the branch-protection / uncommitted-changes problem entirely.
- **Council sync by default:** Revert async-by-default. Use `BASH_DEFAULT_TIMEOUT_MS=300000` in CLAUDE.md for Claude Code compatibility. `--async` stays as opt-in.
- **@mentions parsed from prompt string:** `@member` tokens validated against known members. `@all` queries everyone. Unknown `@mentions` fail loudly. No false positives on code blocks or emails.
- **Design approved stays in state.json:** `kd design approve` already writes to state.json. Just wire `kd status` to display it. No frontmatter migration needed.
- **tk move gets `--to` flag:** `kd tk move <ids>... --to <target>` for multi-ID moves. Single-ID `kd tk move <id> [target]` keeps current behavior.
