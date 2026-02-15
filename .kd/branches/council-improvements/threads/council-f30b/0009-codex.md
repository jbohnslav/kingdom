---
from: codex
to: king
timestamp: 2026-02-15T00:08:50Z
---

Using the `kingdom` skill for this review because it’s a council workflow/design assessment. I’m going to ground feedback in the current code paths (`cli`, `thread`, `config`, `council`) and then give phase-by-phase risks and recommendations.
I confirmed the config schema currently has only `council.members` and `council.timeout`; there is no `council.chat` shape yet, so that part of the design will need explicit schema + validation work. Next I’m inspecting thread write semantics and status/session plumbing to evaluate concurrency and richer state feasibility.
I’ve confirmed thread writes use exclusive create with retries but no explicit thread-level lock, which matters for concurrent auto-mode writes. I’m now checking whether `kd chat` already exists and how council worker failures are surfaced today, so I can call out implementation risks precisely.
I confirmed there is currently no `kd chat` command implemented in `src/kingdom/cli.py`, so Phase 2 is net-new CLI surface, not a revival toggle. I’m doing one more pass over council-related CLI output paths (`show/list/status`, config display) to flag contradictions and sequencing dependencies accurately.
I found existing council/thread/config test suites, so this project already has harnesses for the risky parts. I’ll skim those specific tests to identify blind spots for your proposed phases (especially stream normalization, status states, and concurrent thread writes).
**Key Contradictions And Gaps First**
1. `council.chat` config cannot be added without schema work first. Current validator rejects unknown council keys (`src/kingdom/config.py:98`, `src/kingdom/config.py:174`), so Phase 3 depends on config changes before any runtime work.
2. `/mute` and `/unmute` conflict with “No slash commands” in Non-Goals. This is a direct spec contradiction.
3. “Rename `_print_thread_status`” is stale. The function is currently `print_thread_status` (`src/kingdom/cli.py:690`), not underscored.
4. “Configurable members” is already implemented via `council.members` in `Council.create` (`src/kingdom/council/council.py:38`). Keep as regression hardening, not net-new scope.
5. `watch_thread()` still ignores `.stream-*` (`src/kingdom/cli.py:717`) even though streams are produced (`src/kingdom/council/council.py:111`, `src/kingdom/council/base.py:75`).

**Phase 1 Review (Completeness, Feasibility, Dependencies, Risk)**
- `Completeness`: Missing round model. Many Phase 1 features need explicit “turn/round” identity (retry failed members, show latest turn, status by turn). Today “latest round” is inferred from last king message, which is fragile.
- `Completeness`: Missing targeted-ask semantics in status. `thread_response_status` uses thread members from metadata (`src/kingdom/thread.py:340`), not the latest king message target, so targeted follow-ups in a multi-member thread can report false pending.
- `Completeness`: Missing “in-flight ask” behavior. If a second ask lands before first async completes, status/retry/list can cross wires.
- `Feasibility`: “Richer status derived from process state + logs” is harder than it looks because async worker is detached with `stdout/stderr` to `DEVNULL` (`src/kingdom/cli.py:459` path), and per-member process state is not persisted.
- `Feasibility`: Automatic retry can create duplicate assistant messages unless retry markers are round-scoped and idempotent.
- `Dependencies`: You need a small status state machine before implementing `status`, `retry`, and enriched `list`. Otherwise each command invents its own inference.
- `Risk`: Most likely failure mode is misleading UX: showing “pending” forever when worker crashed; showing “running” from stale stream file; writing `*Error: None*` when response text is empty and error unset (`src/kingdom/council/council.py:125`, `src/kingdom/cli.py:433`).

**Phase 2 Review (Completeness, Feasibility, Dependencies, Risk)**
- `Completeness`: “Open existing thread or create new one” needs collision rules with CLI asks in parallel. You need one writer/orchestrator policy per thread.
- `Completeness`: `@member` semantics are underspecified for multiple mentions and `@all` parity with existing CLI behavior (`src/kingdom/cli.py:377`).
- `Feasibility`: Streaming from `.stream-*` is non-trivial because Codex stream is JSONL events, not display text (`src/kingdom/agent.py:120`); direct file tailing will be noisy.
- `Feasibility`: Current stream write is line-based, not token-based (`src/kingdom/council/base.py:75`), so “alive feel” improves, but not true token streaming.
- `Dependencies`: Build backend stream normalizer before TUI rendering; otherwise your UI code becomes backend-specific and hard to test.
- `Risk`: High risk of racey/misordered panels if CLI and TUI both append to same thread. Thread writes are best-effort collision-safe (`src/kingdom/thread.py:218`) but ordering is by race, not conversational intent.

**Phase 3 Review (Completeness, Feasibility, Dependencies, Risk)**
- `Completeness`: “Each councillor gets full thread context” is underspecified. Current system mostly relies on backend session continuation; explicit thread replay policy is undefined.
- `Completeness`: Stop condition “short/empty responses” needs concrete thresholds and backend-normalized text definition.
- `Feasibility`: “User typing interrupts auto-mode immediately” is hard with blocking subprocess queries. You need cancellable orchestration and kill/cleanup semantics.
- `Dependencies`: Requires Phase 2 normalizer + Phase 1 round/state model first. Otherwise auto-mode state and UI state will drift.
- `Risk`: Highest failure mode is runaway or low-value loops (round-robin hallucinated back-and-forth) plus context bloat.

**Q5: Config Design (`council.chat`)**
Current shape is too thin. I’d add:
1. `enabled` (bool).
2. `mode` (`broadcast` | `sequential`).
3. `auto_rounds` (int).
4. `poll_ms` (int) for UI poll cadence.
5. `interrupt_policy` (`cancel_running` | `queue_user`).
6. `stop` object, e.g. `min_chars`, `all_empty_rounds`.
7. `retry` object for Phase 1 parity (`max_attempts`, `backoff_ms`, `reset_session_on_retry`).
8. `auto_commit` mode (`off` | `prompt` | `on_success`), if 1e3d stays in this project.

Also: update validation constants and parser in `src/kingdom/config.py` first, or all commands will reject config.

**Q6: Streaming Architecture / Codex JSONL**
- Normalization should live outside TUI, not in UI widgets. Put it in shared council layer used by both `kd council watch` and `kd chat`.
- `parse_codex_response()` (`src/kingdom/agent.py:120`) is final aggregation; it is not enough for incremental display. You need incremental event parsing from each JSONL line.
- Recommended normalized frame model: `member`, `kind` (`token`, `message`, `status`, `error`), `text`, `timestamp`.
- Parse rules:
1. Codex: consume JSONL; render only `agent_message` content and explicit error/status events.
2. Claude/Cursor: treat as plain text/JSON final output depending stream source.
- Keep raw stream files untouched for debugging; render normalized view only.

**Q7: Thread System For Group Chat / Concurrency**
- Current file-per-message model is workable.
- `add_message` uses exclusive create with retry (`src/kingdom/thread.py:218`), so collisions are mitigated but ordering is race-dependent.
- For auto-mode, avoid concurrent writers per round. Use a single orchestrator loop that serializes writes.
- For status/retry/pagination, you need explicit round markers, not just “last king message” inference (`src/kingdom/thread.py:340`).
- Without round metadata, retries and partial failures will be ambiguous.

**Q8: Textual Dependency**
- Reasonable choice for a real chat TUI; building this in Rich Live + prompt_toolkit will likely reimplement focus, scrolling, input handling.
- Hidden complexity:
1. Async task lifecycle and cancellation.
2. Poll + render throttling with large streams.
3. Clean teardown when workers still running.
4. TUI testing (Textual test harness needed).
- Biggest gotcha: interruption semantics are orchestration complexity, not UI complexity.

**Q9: `/mute` / `/unmute` Contradiction**
You need one policy:
1. Keep strict “no slash commands”: remove `/mute`/`/unmute`; move muting to config only.
2. Better option: allow operational slash commands only (`/mute`, `/unmute`, `/help`, `/exit`) and clarify Non-Goal as “no slash commands for persistent config changes.”
Right now the doc says both.

**Q10: Auto-Commit (1e3d)**
Define this explicitly or it will cause pain:
1. Trigger: once a round reaches terminal state (all expected members are `responded|errored|timed_out`).
2. Scope: stage only thread markdown files for that thread (and optionally related `.kd` tracked metadata), never blanket `git add .`.
3. Modes: `off` default, `prompt` interactive, `on_success` optional.
4. Async/no-watch behavior: never block waiting for prompt; either skip or defer to explicit command.
5. Commit message template: include thread id + round id.
6. Guardrails: no commit if no diff; surface hook failures clearly.

I would not commit after each member response. That creates noisy history and race risk during multi-member rounds.

**Recommended Phase Reorder**
1. Phase 0 (foundational): round/state model + config schema extension + shared stream normalizer.
2. Phase 1: CLI reliability/status/retry/show/list.
3. Phase 2: `kd chat` TUI on top of shared primitives.
4. Phase 3: auto group chat mode.

Without that Phase 0, implementation will likely splinter across commands and get brittle quickly.
