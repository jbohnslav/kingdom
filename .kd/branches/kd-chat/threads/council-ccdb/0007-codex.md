---
from: codex
to: king
timestamp: 2026-02-16T19:55:54Z
---

I agree with Claude’s diagnosis, and I’d push it one step further: the wrong primitive is `thread`.

You don’t have 3 chats. You have 3 **job types**:
1. `capture` (backlog idea)
2. `consult` (council query)
3. `execute` (coding run)

If you model those as typed jobs with events, the UI can still show 3 panels, but backend stays simple and you avoid IRC/tmux creep.

What to change:

- Replace free-form “thread” with a `Run` record:
  - `id`, `kind` (`capture|consult|execute`), `ticket_ref`, `status`, `created_at`
- Store append-only events per run (`requested`, `started`, `agent_reply`, `completed`, `failed`)
- Make panels just filtered views over the same event log
- Keep only `execute` interactive/long-lived; `capture` and `consult` should be request/response by default

Guardrails to avoid “reimplementing IRC”:

- No arbitrary channels/rooms
- No user presence model
- No general DM/mentions system
- No long-lived chat state unless `kind=execute`

One place I’d slightly challenge Claude: “idea capture needs no agent” is mostly true, but natural-language capture is still useful. Keep it as a thin async parser (`capture` run), not a dedicated live session.

If you want a minimal rethink, ship only this:
1. `kd run create --kind ...`
2. `kd inbox` (new events across runs)
3. `kd run watch <id>` (only for execute, optional for others)

That gives you multiplexing without building a messaging platform.
