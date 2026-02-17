---
from: claude
to: king
timestamp: 2026-02-17T03:01:59Z
---



Let me check the current state of the design doc and tickets.Alright, here's the status:

**Design doc** is written and looks solid at `.kd/branches/polish/design.md`. It covers the scope we agreed on — existing tickets pulled in, new tickets to create, decisions, and open questions.

**Branch tickets**: 36 tickets pulled in. That includes all the ones we discussed — `efaf` (copy), `ab5d` (mentions), `9725` (colors), `4994`/`19b6` (tk log dups), `ca69` (dep bug), `c937` (remove Cursor/Gemini), etc.

**But the new tickets haven't been created yet.** Cursor's batch of `kd tk create --backlog` commands hasn't been run. The design doc lists 23 "New Tickets to Create" items that still need to be turned into actual backlog tickets.

Also a few things to flag:

1. **Scope creep watch** — the design doc still lists `b057` (council writable mode), `3e60` (chat Phase 2), `7afc` (group chat modes), `7a1d` (LLM-to-LLM mentions), and `1fa5` (tk delete) on the branch. Those are features, not polish. We agreed to backlog those. They should be moved back.

2. **The dedup work isn't done** — `19b6` should be closed as dup of `4994`, and `3269` as dup of `3159`.

3. **The open questions in the design doc are stale** — we already decided: tk log is worklog-append (per the doc's own Decisions section), and council writable mode is backlog'd. The remaining question about "one big CLI pass or per-command tickets" — I'd say per-command, it's easier to parallelize.

Want me to create the new tickets and clean up the scope (move features back to backlog, close dups)? Or should we settle the design doc first?
