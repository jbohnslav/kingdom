---
from: claude
to: king
timestamp: 2026-02-16T20:08:09Z
---

You're right that the Hand's role gets awkward here. Let me think about what it actually is today versus what it becomes.

**The Hand today:** It's the agent the King talks to directly — the one running in your terminal, reading tickets, writing code, running tests. It's "Claude Code in the context of a kd branch."

**The Hand in a Council-as-Supervisor world:** If the Council is dispatching peasants and filing tickets, what's the Hand doing? It's... the King's terminal session. It's the CLI itself.

I think the Hand doesn't get deprecated — it gets **demoted to the default peasant**. Or more precisely, it loses its special status and becomes one of two things:

1. **The King's direct tool.** When you want to do something yourself — poke at code, run a one-off command, investigate a bug — you're using the Hand. It's `kd work` without a ticket. Unstructured, interactive, exploratory.

2. **The Council's executor.** When the Council dispatches work, those are peasants. The Hand is never dispatched — it's the session you're sitting in.

So the taxonomy becomes:

| Role | What it does | Who controls it |
|---|---|---|
| **King** | Sets direction, approves actions | Human |
| **Council** | Advises, proposes actions, supervises peasants | Multi-model, policy-gated |
| **Peasant** | Executes scoped ticket work | Council (or King directly) |

The Hand just... dissolves into the CLI. It was always "the agent the King is talking to," and that's just whatever `kd` session is active. It doesn't need a name.

The one thing the Hand concept *did* provide was a distinguished "trusted agent" — the one that gets to do things peasants can't (merge, close tickets, change design). But in the new model, that trust boundary moves to the **policy layer**. The Council proposes, the King approves, and the executor (peasant or CLI) just runs the approved action. Trust lives in the permission model, not in which agent has the title "Hand."

**Practical implication:** I'd stop using "Hand" in new code and docs. Don't rip it out of existing code — that's churn for no value. But new features (the action ledger, `kd act`, `kd supervise`) shouldn't reference it. If anyone asks "what's the Hand?" the answer is "it's the old name for your terminal session."

Does that match your instinct, or do you see the Hand retaining a distinct role?
