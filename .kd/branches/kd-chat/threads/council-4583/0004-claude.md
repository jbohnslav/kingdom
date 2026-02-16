---
from: claude
to: king
timestamp: 2026-02-16T19:04:02Z
---



Let me understand the current session architecture before advising.Excellent. That's a thorough map. Now let me also check what `query_once` does with `self.base` and `self.branch` — specifically in the chat context — since those get set on mount.There it is. The chat TUI sets `member.base` and `member.branch` on every council member during `on_mount()` (line 167-168). That means every `query_once()` call from the TUI writes `pid` to the shared `sessions/{agent}.json` file via `update_agent_state()`. Meanwhile a concurrent `kd council ask` in another terminal is calling `load_sessions()` / `save_sessions()` on the *same files* — writing `resume_id`, `status`, etc.

Let me confirm the chat doesn't accidentally update `resume_id` too.Line 207-208: `query_once()` updates `self.session_id` in memory. The TUI never calls `save_sessions()`, so this never gets persisted to disk from the chat path. But importantly — the *non-chat* path does: `worker.py:69` calls `c.save_sessions()` after every query, and `cli.py:442/523` does the same.

Now let me verify one more thing — whether `build_command()` passes `session_id` to the agent backend, even when called from chat.Key finding at line 88: `build_command()` passes `self.session_id` to the agent backend. The chat TUI doesn't call `load_sessions()` so `session_id` starts as `None`. But after the first `query_once()` call, `session_id` gets set in memory (line 207-208). Subsequent chat queries for the same member will pass this session ID — so within a single TUI session, there's implicit session continuity via the in-memory `session_id`.

Now I have the complete picture. Here's my analysis.

---

## Analysis: Session Cross-talk Isolation (Ticket 0f27)

### The Problem, Precisely

There are **two concrete cross-talk vectors**, plus one design smell:

**Vector 1: PID clobbering (chat → non-chat)**
The TUI sets `member.base` and `member.branch` on mount (`app.py:167-168`), which causes every `query_once()` to call `update_agent_state(base, branch, name, pid=process.pid)` (`base.py:184`). This writes the chat process's PID into `sessions/{agent}.json` — the same file that `kd council ask` and the peasant harness read/write. A concurrent `kd council ask` that calls `get_agent_state()` to check liveness will see the *chat's* PID, not its own. And the chat PID overwrites whatever PID the non-chat workflow stored.

**Vector 2: resume_id clobbering (non-chat → chat, indirectly)**
The chat doesn't call `load_sessions()` or `save_sessions()`. Good. But it *does* accumulate `session_id` in memory during `query_once()` (line 207-208) and passes it to `build_command()` on subsequent queries. Meanwhile, a concurrent `kd council ask` calls `save_sessions()` which writes a *different* `resume_id` to the same file. If the user later restarts the TUI and the TUI *ever* starts calling `load_sessions()` (e.g., in a future feature), it'll pick up the non-chat resume_id. Today the TUI doesn't load sessions, so this vector is latent — but the shared file is a landmine.

**Design smell: in-memory session_id leaks across chat turns**
Within a single TUI process, `query_once()` captures `session_id` from the agent response and stores it on the member object. The *next* chat query for that member passes this `session_id` via `build_command()`. This means chat queries quietly build session continuity through the agent backend (e.g., Claude Code's `--resume`), even though the design doc explicitly says "Thread-history-only, no session resume." The thread history injection is working correctly, but the agent is *also* getting `--resume` continuity — double context. This is probably harmless today (agents handle duplicate context gracefully), but it's architecturally wrong.

### Answers to Your Questions

**1. What's the right isolation boundary?**

**Per-workflow-type, keyed by role + context.** The session file path should encode the workflow context. Specifically:

- Non-chat council: `sessions/{agent}.json` (current behavior, unchanged)
- Chat: no session files at all. Chat explicitly doesn't use session resume — it uses thread history injection. The member's `session_id` should be `None` for every query, and the TUI should never write to `sessions/`.
- Peasant: `sessions/peasant-{agent}-{ticket}.json` (already scoped by ticket + agent, effectively isolated)

The simplest fix is: **stop the chat from writing PID to session files, and ensure `session_id` stays `None` across queries.** Don't create a new session file hierarchy — just stop the chat from touching the shared one.

Concretely:
- Set `member.base = None` and `member.branch = None` in the TUI's `on_mount()` (or just don't set them). This disables the PID write in `query_once()` line 181-184.
- After each `query_once()` returns, reset `member.session_id = None` — or patch `run_query()` to ignore session IDs. This prevents accidental `--resume` bleed across chat turns.

This is the "chat is stateless" approach and it's the right one given the design doc's explicit decision: "Thread-history-only, no session resume."

**2. Should chat sessions persist within a thread?**

**No.** The design doc already decided this: "Drop `--resume` for group chat entirely. Council is read-only advisory — tool-use context across turns has near-zero value. Thread history injection provides full cross-agent awareness."

Chat doesn't need session continuity because:
- Every query already includes the full thread history via `format_thread_history()`
- Session resume carries single-agent context, which duplicates what's already in thread history
- Chat is read-only (no tool use), so there's no filesystem state to resume

If we ever want chat sessions to persist (e.g., for faster agent warm-up), the right approach would be per-thread session files (`threads/{thread_id}/sessions/{agent}.json`), completely separate from the branch-level session files. But that's a future consideration, not needed now.

**3. Chat open + `kd council ask` in another terminal?**

**Fully isolated. No shared context.** They should operate independently:
- Chat reads/writes thread message files (its own thread directory)
- `kd council ask` reads/writes its own thread + branch-level session files
- Neither should touch the other's session state

The only shared resource is the agent *binary* (e.g., `claude` CLI). Two processes can invoke it concurrently without conflict — each gets its own subprocess.

If the user runs `kd council ask` targeting the *same thread* that chat has open, the chat will pick up the responses via its poller (this is the intended interop described in the design doc). But session state stays separate — the council ask uses `--resume` from branch sessions, the chat uses thread history injection.

**4. Edge cases and failure modes:**

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Chat + `kd council ask` running concurrently on same thread | Message sequence contention | Already handled: `add_message()` uses exclusive-create (`'x'` mode) with retry. No risk. |
| Chat kills a process via Escape while `kd council ask` is also running same agent | Wrong process killed | Chat only kills `member.process` — the Popen handle it launched. It won't kill the council ask's process because that's a different Popen in a different Python process. Safe. |
| PID in session file points to chat's dead process; `peasant_start` checks liveness | False "already running" | Fix by not writing PID from chat. Or the liveness check uses `os.kill(pid, 0)` which would return False for a dead process. Low risk but still a correctness bug. |
| Chat restarts, agent's in-memory `session_id` is lost | Loss of `--resume` context | This is desired behavior — chat should be stateless. Thread history provides continuity. |
| Future feature adds `load_sessions()` to chat | Silently inherits non-chat resume_id | Document explicitly: "Chat MUST NOT call load_sessions/save_sessions." Add an assertion or code comment. |
| Agent returns a session_id that the chat ignores | Wasted agent-side session state | Harmless. Agent backends garbage-collect old sessions. |

### Recommended Implementation

The fix is surgical — two changes, both in `app.py`:

1. **Don't set `member.base` and `member.branch`** in `on_mount()`. Remove lines 167-168. This stops chat from writing PIDs to shared session files. If you want PID tracking for chat processes specifically, write to a chat-specific location (e.g., `threads/{thread_id}/.pids/`), but honestly for Phase 2 you probably don't need it.

2. **Reset `session_id` after each query** to prevent `--resume` leaking across chat turns. In `run_query()`, after the `asyncio.to_thread()` call returns, add `member.session_id = None`. Or alternatively, save and restore: capture `member.session_id` before the query, restore it after. The simplest approach is just always clear it.

That's it. No new file hierarchies, no schema changes, no migration. The chat becomes a fully stateless view over thread files, as the design doc intended.

For the tests: create a fixture that simulates concurrent chat + council-ask by having both write to the same session file, and verify they don't interfere. The key assertion is: after a chat query runs, `sessions/{agent}.json` should be unchanged from before the chat query started.
