---
from: claude
to: king
timestamp: 2026-02-17T01:27:59Z
---

Good framing. Let me think about this practically.

## In This PR (Polish Branch)

These are all small, self-contained, low-risk improvements:

**Ticket CLI polish:**
- `kd tk log` (the core command — already have two tickets for it)
- `kd tk show` Rich panel layout
- `kd tk list` Rich table formatting
- `kd tk list` summary counts / progress bar
- `kd tk current` command
- Standardize success/warn/error message templates
- Add "next step" hints on successful commands
- Improve empty-state messages
- `kd tk move` clarify success message
- `kd tk close` accept optional reason message
- `kd tk close` show newly unblocked tickets
- `kd tk create` print the created file path
- `kd tk create --backlog` confirm where ticket landed

**Chat TUI polish:**
- Copy-to-clipboard action (efaf, already exists)
- Reply button with quoted context + @author
- @mentions tab-complete and colored rendering (ab5d)
- Brand-aware default member colors (9725)
- Thinking duration formatted as mm:ss
- Error panel with retry hint
- Slash command discoverability
- Auto-scroll improvement (don't snap while reading)
- Expand color palette beyond 6

**CLI output consistency:**
- Replace raw `print()` with `console.print()`
- Standardize error output styling
- Cleaner Ctrl+C messaging
- `kd done` structured summary panel

**Council (non-permissions):**
- Council status symbol legend
- `kd council show --last N` for long threads

## Backlog (Not This PR)

**Council permissions** — Agree with your instinct. The capability matrix, writable mode, tool allowlists, confirmation gates, audit logging — that's a feature, not polish. Big blast radius, needs its own design pass.

Your idea about the simpler version is smart though: just drop Gemini (it ignores boundaries anyway), and rely on instruction-following from Opus and Codex. "Don't act unless I say 'open the ticket'" is a behavioral convention, not a permissions system. That costs zero code and gets you 80% of the value. We can backlog the formal permissions work for when the convention breaks down.

**Also backlog:**
- `tk log` advanced filters (--since, --actor, --type, --follow) — core `tk log` is in scope, but the filter flags are a separate pass
- Mentions fuzzy matching, ranking by recency, Shift+Tab cycling — the basic tab-complete + coloring is enough for this branch
- Colorblind-safe palette, NO_COLOR/TERM=dumb, truecolor detection — nice but niche
- Snapshot/golden tests for colored output — useful but not user-facing polish
- All the accessibility items (screen reader labels, reduce-motion) — important but a different initiative

That puts roughly **25-30 small tickets** in this PR — each one independently shippable, most under half a day. Want me to pull that into the design doc?
