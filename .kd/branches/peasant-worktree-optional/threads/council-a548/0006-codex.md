---
from: codex
to: king
timestamp: 2026-02-12T23:14:40Z
---

Your request is clear: add an execution-mode choice after planning, where each peasant can either run tickets in parallel via worktrees or the preferred coding agent can execute tickets serially on `main`. I’m going to quickly inspect the current workflow docs/code so I can map this cleanly to your existing design instead of proposing something generic.
I found strong signals that this is already partly implemented: `peasant start` has a `hand` mode path that uses the base repo instead of creating a worktree. Next I’ll read the relevant CLI/doc sections and map them into a clean workflow model you can use.
I’m now checking the exact behavior around review/accept and how `--hand` interacts with worktree-only commands, so I can give you a concrete fit-gap map and not hand-wave.
I have enough context to map this directly. I’ll now give you a concrete “fit with current system” model, including what already exists (`--hand`) and the small gaps to close so serial-on-main is safe and first-class.
This fits cleanly as an execution-mode switch in the **development** phase, while keeping planning/design/breakdown unchanged.

You already have both primitives:

- Parallel per-ticket workers via worktrees is the default (`kd peasant start <ticket>`): `src/kingdom/cli.py:1049`
- Serial “Hand does it in current checkout” exists as `--hand`: `src/kingdom/cli.py:1053`
- `--hand` behavior is tested: `tests/test_cli_peasant.py:81`
- This matches your design goal of parallel peasant execution with supervision: `docs/multi-agent-redesign.md:20`

How it should map to workflow:

1. Design + council iteration (unchanged)
2. Breakdown into tickets (unchanged)
3. Choose execution mode:
- `parallel`: one peasant per ready ticket in separate worktrees
- `serial-hand`: Hand runs one ticket at a time in current checkout (no worktree branch merge step)
4. Review/close ticket (same quality gates), then continue queue

Main gaps to make this first-class:

- Mode is per-command today, not run-level policy.
- `--hand` is not enforced serially; you could accidentally run multiple workers in same tree.
- Reject/relaunch path assumes a worktree path, which is wrong for hand mode: `src/kingdom/cli.py:1533`
- Worktree-only commands (`sync`, `clean`) need explicit “not applicable in serial-hand mode.”

If you want, I can implement the minimal version next:
1. Add run-level `execution_mode` (`parallel` / `serial-hand`) in state.
2. Add guard: only one active hand worker at a time.
3. Persist actual workspace path in session state and use it on relaunch/review.
4. Add a simple `kd peasant start-ready` that fans out in parallel or runs one-at-a-time based on mode.
