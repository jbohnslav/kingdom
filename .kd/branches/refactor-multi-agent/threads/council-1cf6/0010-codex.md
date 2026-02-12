---
from: codex
to: king
timestamp: 2026-02-09T17:13:56Z
---

I’ll do a focused design review against the current `design.md`, then give you a prioritized “what’s next” list based on remaining risks and unfinished acceptance criteria, with no code edits.
1. **High: Council UX is internally inconsistent in the doc**
`design.md` says default `kd council ask` is interactive and streams inline (`.kd/branches/refactor-multi-agent/design.md:248`), but also says inside Claude Code it backgrounds and output is not visible (`.kd/branches/refactor-multi-agent/design.md:251`). It also proposes async `ask + show --wait` as the better design (`.kd/branches/refactor-multi-agent/design.md:255`) while command surface now introduces `watch` (`.kd/branches/refactor-multi-agent/design.md:243`).
This needs one canonical contract.

2. **Medium: T4 acceptance checklist does not reflect “council fixes completed”**
All council acceptance items are still unchecked in T4 (`.kd/branches/refactor-multi-agent/design.md:399`). If fixes landed, design status is stale and hard to trust for planning.

3. **Medium: Peasant “done” criteria vs execution policy is underspecified**
Stop condition says done requires tests + ruff pass (`.kd/branches/refactor-multi-agent/design.md:308`), but harness policy says agent runs checks “when it makes sense” (`.kd/branches/refactor-multi-agent/design.md:305`). This can still allow false “done” unless harness enforces gates.

4. **Medium: Worktree freshness is mentioned but not operationalized**
`kd peasant sync` exists in command surface (`.kd/branches/refactor-multi-agent/design.md:269`) but no acceptance criteria ties freshness checks to `start/review/done`, so staleness regressions can recur.

## What’s next (priority order)

1. **Close T4 properly (Council hardening + doc truth update).**
Pick one UX contract and encode it clearly:
- Recommended: `kd council ask` default async fast return, `--wait` for inline streaming, `kd council watch` for reattach/live tail.
Then mark completed acceptance items that are truly done.

2. **Finish T3 (session/state primitives).**
T3 is foundational and still entirely open (`.kd/branches/refactor-multi-agent/design.md:386`). Without reliable session state, council/peasant lifecycle behavior stays brittle.

3. **Do T6 next (supervision loop).**
`msg/read/review` acceptance is still open (`.kd/branches/refactor-multi-agent/design.md:435`). This is the operator control plane; it should follow immediately after council stability.

4. **Add explicit peasant invariants (small v2 patch to design).**
Before more features, codify:
- unified quality gates for done/review,
- mandatory worktree bootstrap (`uv sync`, `pre-commit install`),
- reject auto-relaunch behavior,
- freshness/staleness checks tied to lifecycle events.

If you want, I can draft a concise “Design v3.1” section that resolves item 1 and item 4 textually so the doc becomes implementation-ready.
