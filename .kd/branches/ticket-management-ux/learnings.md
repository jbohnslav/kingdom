# Learnings: ticket-management-ux

## Agent Experience Using the kd Workflow

This was the first time an agent (Claude Code, Opus 4.6) drove the full kd
lifecycle end-to-end: start → design → council → tickets → implement → review.

### What worked well

- **Council feedback was genuinely useful.** The three members (claude, codex,
  cursor) caught real bugs I missed: the two-pass pull issue, the `kd tk start`
  not restoring archived tickets, and the duplicate-ID crash. Worth the ~2min
  wait each time.

- **The design-first flow forced clarity.** Writing the design doc before coding
  made the council review much more productive — they could read the file and
  give concrete feedback against stated decisions rather than guessing intent.

- **Ticket status tracking kept things organized.** `kd tk start` / `kd tk close`
  gave a clear sense of progress. `kd tk list` showed what was done vs remaining.

- **Async council dispatch is the right default.** The watch mode polls and
  renders panels as they arrive, so you see fast responders immediately instead
  of waiting for the slowest one.

### Friction points

- **No `kd tk pull` yet (bootstrapping problem).** Had to use `kd tk move <id>
  <branch>` to pull backlog tickets — the thing we were building. Felt awkward
  but unavoidable.

- **`kd tk move` requires the branch name, not "current branch".** Would be
  nicer if it defaulted to the active run's branch, or if pull existed from
  the start.

- **Council thread messages need trailing whitespace cleanup.** The pre-commit
  hook caught trailing whitespace in council response files twice. The council
  worker should strip trailing whitespace before writing message files.

- **Committing `.kd/` state is manual and easy to forget.** After every
  `kd tk close`, council ask, or ticket move, you need to `git add .kd/ &&
  git commit`. Could be automated or at least prompted. It's especially easy
  to forget the council thread files.

- **No way to see the full workflow status at a glance.** `kd status` shows
  ticket counts but not which tickets are open/closed or what council threads
  exist. A richer status command would help.

- **`kd tk create` used to print just the ID.** This was the #1 thing I wanted
  to fix — as an agent, I need the path to edit the file. Printing the absolute
  path is much more useful for both agents and `vim $(kd tk create ...)`.

- **Design doc has no formal "approved" state.** After council review, I updated
  the design doc and committed it, but there's no `kd design approve` or similar
  to mark it as reviewed. The design doc just exists as a file.

### Observations for future agent integration

- An agent running `kd work` in hand mode would benefit from the full workflow
  being scriptable: create branch, start run, pull tickets, work, close, done.
  Most of this works today but some steps (like writing the design doc) require
  manual editing.

- Council reviews are most valuable when given specific instructions ("review
  against tickets", "check for bugs in this diff") rather than open-ended asks.

- The two-council-ask pattern (design review, then code review) caught different
  classes of issues. Design review caught missing requirements (reopen behavior,
  fail-fast semantics). Code review caught implementation bugs (partial moves,
  duplicate IDs).
