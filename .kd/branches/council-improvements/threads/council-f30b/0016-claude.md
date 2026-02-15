---
from: claude
to: king
timestamp: 2026-02-15T02:52:21Z
---

This looks solid. You incorporated the feedback well. A few remaining observations:

### What you got right

- **d09d merged into 70f6** — clean merge, 70f6 now captures both pagination and visual separation with a "Note: Subsumes former ticket d09d" at the bottom.
- **1e3d now depends on e756** — avoids the worker.py merge conflict.
- **6412 now has the watch streaming criterion** — the most impactful UX fix has a home. Wording is specific: "tails `.stream-{member}.jsonl` files, extract `text_delta` text, show accumulated text per member, replace with final response."
- **3e60 is substantially fleshed out** — thread resumption, slash commands, optional dependency, color-coded panels, asyncio bridge, explicit Phase 3 deferral.
- **a4f5 dropped the a9c9 dependency** — now standalone, uses thread-based status only. AC #3 is specific about how errored state is detected ("message body content, not a structured error field").
- **a9c9 tightened up** — AC #2 now says "concrete runtime metadata" and maps each state to a specific check (PID liveness, exit code, message presence). No more hand-waving.

### Three small things still worth noting

**1. a9c9 doesn't specify where the PID gets recorded.** The ticket says "worker PID liveness (`os.kill(pid, 0)`)" but the current async worker is spawned as a single process for all members (`worker.py` calls `query_to_thread()` which runs all members in threads inside one process). That one PID tells you "the worker is alive" but not *which member* is running vs. done vs. errored. To get per-member status, you either need:
- One worker process per member (spawn 3 subprocesses instead of 1), or
- The single worker writes per-member status markers to disk as each member starts/finishes/errors

This is an implementation decision, not a ticket wording problem. But the implementer should be aware that "check PID" gives you worker-level liveness, not member-level. The log file parsing (exit code, error markers) is what actually gives per-member granularity. Consider adding a note to the ticket that the PID check is for the worker process, and per-member state comes from log file parsing.

**2. 1e3d's `council.auto_commit` config key needs the config schema update.** The current `VALID_COUNCIL_KEYS` in `config.py:98` is `{"members", "timeout"}`. Adding `auto_commit` requires updating validation. This is small work but it's a dependency the implementer needs to know about. Either add an AC like "Add `auto_commit` to `CouncilConfig` dataclass and validation" or just trust the implementer to figure it out. Not a big deal — just noting it.

**3. 70f6's `--last N` wording.** The proposal says "N turns" but the AC says `--last N` without specifying the unit. The proposal section says "turns (not messages)" which is correct, but it would be clearer if AC #2 said `--last N` shows the last N turns explicitly. Minor — the proposal section makes the intent clear.

### Dependency graph looks correct

```
e756 (no deps) ─┬─→ 6412
                 ├─→ 1e3d
                 └─→ 3e60

a9c9 (no deps, standalone)
70f6 (no deps, standalone)
a4f5 (no deps, standalone)
```

This is a clean DAG. e756 is the only blocker. Once it's done, 6412 (P1) is the next priority, then the four P2 tickets can be done in any order. 3e60 is naturally last because it's the biggest and benefits from all the CLI fixes being dogfooded first.

### Verdict

The tickets match the design. Nothing is missing, nothing is unnecessary, and the work is scoped right. Ship it.
