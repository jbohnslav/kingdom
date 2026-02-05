## Recommended Next Steps

1. Make `/breakdown approve` show parsed tickets and ask for confirmation before creating them (or prompt user to run `kd breakdown --apply`)

2. Add a dry-run mode to `kd breakdown --apply` (show what would be created, require `--yes` or interactive confirmation)

3. Make it idempotent - only parse `- [ ]` items (unchecked), skip `- [x]` (already created)

4. Tighten the prompts in `breakdown.py` to enforce the exact format the parser expects

Want me to start implementing these?

you> no, just put your current knowledge and code pointers into a new markdown design document.
I've prepared a comprehensive design document at `docs/design_breakdown_finish.md` that consolidates everything. It includes:

**Current State Summary:**
- What's working: `/design`, `/design approve`, `/breakdown`, council prompting, ticket parsing, basic `kd breakdown --apply`
- What's not: `/breakdown approve` (stub at `hand.py:318-321`), no confirmation before creating tickets, no idempotency

**Key Implementation Steps:**
1. Change the parser regex at `breakdown.py:244` to only match `- [ ]` (not `- [x]`)
2. Extract ticket creation into a shared function
3. Add confirmation prompt + `--yes` flag to `kd breakdown --apply`
4. Implement `/breakdown approve` to show preview and confirm before creating

**Code Pointers:**
- `/breakdown approve` stub: `hand.py:318-321`
- Ticket parsing regex: `breakdown.py:244`
- CLI ticket creation loop: `cli.py:206-236`
- State persistence: `cli.py:237-239`

The doc is waiting for your write permission. You already have two earlier drafts (`docs/design_breakdown_polish.md` and `docs/mvp-next-step-design.md`) that covered parts of this—the new doc consolidates and supersedes them.
