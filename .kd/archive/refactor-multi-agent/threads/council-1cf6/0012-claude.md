---
from: claude
to: king
timestamp: 2026-02-09T17:15:04Z
---



Here's where things stand:

## Implementation Status

| Task | Status | Notes |
|------|--------|-------|
| **T1: Thread model** | **Done** | Fully implemented and tested |
| **T2: Agent config model** | **Done** | Fully implemented and tested |
| **T3: Agent session state** | **Done** | All 6 criteria met. Minor: `set_agent_state` takes an object instead of `**fields`, but `update_agent_state()` provides the kwargs interface |
| **T4: Council refactor** | **Done** | All 10 criteria met — `ask`, `--async`, `--to`, `--thread new`, `show`, `watch`, `list`, old commands removed |
| **T5: Peasant execution** | **Done** | All 12 criteria met — harness loop, start/status/logs/stop, thread messages, sessions |
| **T6: Peasant messaging** | **Done** | All 4 criteria met — `msg`, `read`, `review` with accept/reject |

## What's Next

Everything in the design doc breakdown (T1–T6) is implemented. The question is: **what's left before this branch merges?**

Based on the design doc, I see these gaps between "code exists" and "ready to ship":

### 1. Smoke testing the full workflow end-to-end
The pieces are all built individually. Has anyone actually run the full cycle?
- `kd council ask "question"` → responses arrive in thread → `kd council show` displays them
- `kd peasant start KIN-XXX` → peasant works → `kd peasant msg` → peasant picks up directive → signals done → `kd peasant review --accept`

This is where real bugs hide — integration seams between T1–T6.

### 2. The council UX question you just raised
You updated the design doc to add `--async` and `kd council watch`. Those are implemented. But the core tension you described — **making council feel natural inside Claude Code's TUI** — might need hands-on testing. Specifically:
- Does the streaming mode (default `ask` without `--async`) actually stay foreground in CC?
- Does `kd council watch` render correctly when CC runs it?
- Is the two-command `--async` + `watch` flow smooth enough, or does it need polish?

### 3. No open tickets remain in the breakdown
T1–T6 cover the full scope. The design doc's "What We're NOT Building (v1)" section is clear. Unless you want to add something beyond the breakdown (like `kd status` showing agents, or improvements surfaced during smoke testing), the code work is done.

**My read:** The implementation is complete against the spec. The next step is integration testing the real workflows — especially the council-inside-CC interaction that prompted your earlier question. That'll surface the real polish items.
