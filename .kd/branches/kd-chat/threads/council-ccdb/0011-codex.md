---
from: codex
to: king
timestamp: 2026-02-16T19:59:24Z
---

I think this is the right direction, and I’d sharpen it:

You don’t need a messaging redesign, but you do need an **authority redesign**.

`threads/` can stay as transcript storage. The missing primitive is a typed **action ledger** the Council writes to, with policy-enforced execution.

1. Council outputs `proposed_action` records (`spawn_peasant`, `file_backlog`, `check_status`, `replan`, `merge`, etc.).
2. Policy classifies each action: `auto`, `requires_approval`, `forbidden`.
3. A small dispatcher executes allowed actions and appends `action_result` events.
4. King works from an inbox of approvals/exceptions, not 3 live panels.

I’d challenge one part of Claude’s take: waiting until peasant loop is “done” risks baking in the wrong control boundary. You can keep the current UX and still add this control plane now, incrementally.

Minimal rollout:
1. Add action types + policy (no new UI).
2. Allow only low-risk auto actions (`file_backlog`, `status_check`).
3. Gate high-risk actions (`merge`, scope changes, ticket close) behind King approval.

That gets you Council-as-supervisor without drifting into IRC/tmux territory.
