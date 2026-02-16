---
from: codex
to: king
timestamp: 2026-02-15T23:55:22Z
---

Using the `kingdom` skill for this audit pass. I’ll inspect `kd design`, ticket state, and the implemented `kd chat` code/tests, then run a small real CLI integration flow to verify behavior before recommending close/reopen actions.
I’ve confirmed design is approved and only 5 branch tickets remain open. Next I’m inspecting all branch ticket files (including closed ones) and the implemented `kd chat` code/tests to assess what’s truly done vs planned.
I’ve confirmed which tickets are closed/open and located the new TUI test/code files. I’ll now inspect the implemented modules (`cli`, `config`, `council`, `tui`) and then run focused tests plus a real `kd chat` CLI smoke flow.
I found several potential behavioral mismatches in the new TUI code, including one critical path that may prevent TUI-originated responses from ever being persisted. I’m validating those with targeted tests and quick reproductions before recommending ticket reopen actions.
Targeted tests pass, but I still need runtime verification of two suspected edge-case bugs. I’m rerunning minimal reproductions with a writable `UV_CACHE_DIR` to avoid sandbox cache permissions.
I’ve confirmed two concrete runtime bugs with direct reproductions. I’ll now do one live `kd chat` CLI smoke run (start + interrupt) to validate the command path in real usage, then I’ll map findings to ticket close/reopen recommendations.
I confirmed branch-related regressions that map to already-closed P1 tickets. I’m going to reopen the affected tickets and append concise worklog notes with repro details, per your instruction.
**Current Verdict**
Implementation is on the right track, but Phase 1 is not fully complete yet.
Core scaffold works; key lifecycle behavior is still broken in real use.

**What I reviewed**
1. Design: `kd design show` (`.kd/branches/kd-chat/design.md`)
2. Tickets: `kd tk list`, `kd tk list --include-closed`, `kd tk show` on branch tickets
3. Code: `src/kingdom/tui/app.py`, `src/kingdom/tui/poll.py`, `src/kingdom/tui/widgets.py`, `src/kingdom/config.py`, `src/kingdom/council/base.py`, `src/kingdom/cli.py`
4. Tests: `uv run pytest tests/test_tui.py tests/test_tui_poll.py tests/test_tui_widgets.py tests/test_config.py tests/test_council.py -q` (181 passed)
5. CLI smoke: launched real `kd chat --new` (thread `council-5b18`) and confirmed TUI boots; also checked `kd chat does-not-exist` returns expected error.

**Bugs found (branch-related)**
1. TUI query path does not persist finalized councillor messages to thread files.
`src/kingdom/tui/app.py:215` runs `member.query(...)` but never calls `add_message(...)` for success paths.
Impact: TUI-originated replies are not written to thread history; lifecycle cannot reliably reach finalized message panels for those queries.
2. Poller blocks later streaming rounds after first finalized response per member.
`src/kingdom/tui/poll.py:117` adds member to `finalized_members`; `src/kingdom/tui/poll.py:129` skips those members forever; no reset between turns.
Impact: subsequent `.stream-{member}.jsonl` updates are ignored in later turns.
3. Preamble config is still not active in command-building path.
`src/kingdom/config.py:50` has `preamble`; `src/kingdom/council/base.py:75` still uses hardcoded `COUNCIL_PREAMBLE`.
This is currently tracked by open ticket `8461`, so this is expected-but-incomplete vs design.

**Ticket actions I took**
1. Reopened `4a91` and added worklog entry.
2. Reopened `fe84` and added worklog entry.
3. Reopened `0245` and added worklog entry.

You can see the updated statuses in `kd tk list --include-closed`:
- `4a91` now open
- `fe84` now open
- `0245` now open

No unrelated (non-branch) bugs were found that warranted a new backlog ticket.

**Intent vs implementation**
1. King’s intent match: partial.
You now have a real `kd chat` command and TUI shell, but not yet a reliable persistent group-chat UX.
2. Plan match: mostly good structurally, incomplete functionally.
Closed tickets covered scaffolding well, but three P1 closures were premature due lifecycle regressions.
3. Feature status:
- Works: command surface, thread open/new/list behavior, TUI boot/layout, polling/event plumbing, config validation for `auto_rounds/mode`.
- Not done yet (open tickets): interrupt semantics (`d869`), slash commands (`3642`), history injection (`213e`), auto-turn scheduler (`3b76`), configurable preamble (`8461`).
- Broken in P1 flow: finalized persistence for TUI-originated responses, multi-turn polling behavior.

**Code quality notes**
1. Overall structure is clear and modular (`tui/app.py`, `tui/poll.py`, `tui/widgets.py` split is good).
2. Main simplification/correctness target: unify “query -> persist -> render” flow so `run_query` always writes thread messages.
3. Edge-case risk: `color_for_member()` uses Python `hash()`, which is process-randomized; colors may vary across runs.
4. Efficiency risk: polling scans all message files every 100ms (`src/kingdom/tui/poll.py:91`), which may degrade on large threads.

If you want, I can do one more pass focused only on the reopened tickets and propose a minimal fix order for fastest return to a truly working Phase 1.
