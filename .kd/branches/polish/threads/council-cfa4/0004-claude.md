---
from: claude
to: king
timestamp: 2026-02-17T01:20:53Z
---



Let me start by reading the design doc and backlog to understand what's already there.That's a lot of backlog tickets. Let me read them all to understand what already exists, and also explore the codebase to find polish opportunities.Alright, I've got a comprehensive view now. Let me cross-reference the existing backlog against what the King asked for and what the codebase exploration turned up. Here's my big list, organized by category:

---

## Polish Branch — Candidate Tickets

### Already in Backlog (relevant to this branch)

These existing backlog tickets fit the "polish" theme:

**Chat TUI:**
- **efaf** — Add copy-to-clipboard action for each council message
- **ab5d** — @mentions should autocomplete (tab-complete) and render in the member's color
- **9725** — Use brand-aware default member colors (Claude orange, explicit Cursor/OpenAI choices)
- **3e60** — kd chat Phase 2 (interactive multi-agent chat TUI)
- **8dea** — kd chat Textual polish pass: research best-in-class apps and prioritize UX improvements
- **7a1d** — LLM-to-LLM @mentions in kd chat round-robin
- **7afc** — Group chat modes: natural order, pooled order, manual

**Ticket CLI:**
- **4994** / **19b6** — Add `kd tk log` command (duplicate tickets)
- **1fa5** — Add `kd tk delete` command
- **f172** — `kd tk close --duplicate-of <id>` to mark duplicates
- **5391** — `kd tk close` should accept an optional reason message
- **b924** — `kd tk close` should show newly unblocked tickets
- **9fd5** — `kd tk list`: group or filter by status
- **d739** — `kd tk list --backlog` should support `--priority / -p` filter
- **021e** — `kd tk list` should show dependency arrows or indentation
- **3159** / **3269** — `kd tk list`: show summary counts / progress bar
- **3c59** — `kd tk current` — show the currently in-progress ticket
- **f279** — `kd tk show`: display dep status inline
- **03b1** — Add `kd tk undep` command
- **2def** — `kd tk create` should print the created ticket file path
- **db2e** — `kd tk create --backlog`: confirm output should say where ticket landed
- **c1c7** — `kd tk ready` should prioritize branch vs backlog tickets
- **ca69** — Bug: `kd tk dep` overwrites existing deps instead of appending

**Council:**
- **b057** — Allow opt-in writable mode so members can edit files when requested (**this is the "council members have more permissions" one**)
- **1c4b** — Add `kd council review` as shortcut for code review asks
- **c247** — Hard to find the right thread when auto-pickup fails
- **1e3d** — Auto-commit council thread files after all members respond
- **9124** — Add error/complete metadata to thread message frontmatter
- **e880** — Council config schema: add `council.chat` and `council.auto_commit` validation

**Config / Session:**
- **9cc9** — `kd config show` should indicate source (config file vs defaults)
- **efed** — Auto-detect active session from branch name without requiring `kd start`
- **d04c** — Add `--verbose / -v` flag to kd commands for debug output

**Other:**
- **12c6** — Move `is_error_response()` from cli.py to thread.py (code hygiene)

### New Tickets to Create

These came from the codebase exploration and aren't in the backlog yet:

**Chat TUI:**
1. **Chat: reply/quote button on messages** — Add a reply action that quotes the original message and @mentions the sender
2. **Chat: slash command discoverability** — Show available slash commands in the UI (tooltip, autocomplete, or hint bar), not just buried in `/help`
3. **Chat: better thinking panel elapsed time formatting** — Show "1m 23s" instead of "83.2s" for durations over a minute
4. **Chat: error panel should show context and retry hint** — Currently just shows "errored" or "timed out" with no guidance
5. **Chat: expand color palette beyond 6 fallback colors** — 7+ agents will share colors; add more distinct options

**CLI Output Consistency:**
6. **Standardize error output styling** — Replace `typer.echo("Error: ...")` with consistent Rich-styled errors across all commands
7. **Standardize "no results" messages with next-step guidance** — e.g., "No tickets found. Create one with `kd tk create`"
8. **Replace print() calls with console.print()** — Several places use raw `print()` instead of Rich console
9. **Standardize success message format** — Consistent use of arrows, emoji, punctuation across commands

**Ticket CLI:**
10. **`kd tk list` should use Rich table formatting** — Current single-line bracket format is hard to scan
11. **`kd tk show` should use structured Rich panel layout** — Ad-hoc field display is inconsistent
12. **`kd tk move` success message uses opaque `parent.parent.name`** — Clarify with human-readable location names

**Council:**
13. **Council status symbols need a legend** — State symbols are cryptic without explanation
14. **Council show should support pagination or `--last N` for long threads** — Huge markdown dumps are hard to read

**General UX:**
15. **Add confirmation prompts for destructive operations** — `peasant clean`, ticket deletions, etc.
16. **Peasant sync should show progress feedback** — Currently silent during git operations
17. **Standardize terminology: "branch" vs "feature", "thread" vs "session"** — Inconsistent across help text
18. **Better help text for "hand" mode** — Term is unclear to new users; document or rename to "serial"/"direct"
19. **`kd done` should show a structured summary panel** — Instead of multiple `typer.echo()` calls
20. **Worklog timestamps should include date context** — `[HH:MM]` loses meaning on old entries

---

That's roughly **50 polish items** — 30 already in backlog, 20 new. The King specifically called out:

- `tk log` — **4994/19b6** (exists, deduplicate)
- Reply and copy buttons in chat — **efaf** (copy exists), **reply is new**
- @mentions tab-completing and colored — **ab5d** (exists)
- Colors by default to brand ID — **9725** (exists)
- Council members have more permissions — **b057** (exists)

Want me to pull these into the design doc and prioritize them into tiers? Or should we create the new backlog tickets first and then curate the branch ticket set?
