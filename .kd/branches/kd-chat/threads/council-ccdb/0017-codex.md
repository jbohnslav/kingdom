---
from: codex
to: king
timestamp: 2026-02-16T20:08:27Z
---

Claude’s mostly right, but I’d keep `Hand` as a control-plane role, not a chat role.

`Hand` should mean: **the privileged executor lane**.

- `Council`: proposes actions.
- `Peasants`: execute scoped, unprivileged ticket work.
- `Hand`: executes high-trust actions after policy + King approval.

That gives you a clean boundary:

1. `auto` actions (`ticket_create`, `status_check`) execute via dispatcher.
2. `requires_approval` actions (`merge`, `ticket_close`, `scope_change`) route to `Hand`.
3. `forbidden` actions are rejected.

So I would not deprecate Hand yet. I would **redefine** it from “agent King chats with” to “trusted execution context.” The King may still drive it interactively, but its real purpose is policy-governed execution of sensitive actions.

Practical docs/API move:

- Keep term internally for now (avoids churn).
- Externally present it as `operator session` if “Hand” feels confusing.
- Bind approvals to this lane in `kd act`/`kd supervise` so audit trails stay crisp.
