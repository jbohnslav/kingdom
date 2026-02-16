---
from: codex
to: king
timestamp: 2026-02-16T19:03:24Z
---

Using the `kingdom` skill for this architecture question. I’ll quickly inspect the current session/thread handling (`session.py`, chat/council entry points, and ticket `0f27`) so recommendations are concrete and compatible with the existing code.
I confirmed ticket `0f27` and current `session.py` behavior. I’m taking one more quick read of `harness`/`cli` session usage to recommend the right isolation model across chat, council, and peasant without breaking existing workflows.
I have enough to answer the architecture questions. I’ll do one final check of the current `ChatApp` turn-selection path so the recommendations align with the latest behavior on this branch.
The root issue is an isolation mismatch: `resume_id` and runtime status share one per-agent branch file (`src/kingdom/session.py`), while multiple workflows mutate it concurrently (`src/kingdom/cli.py:375`, `src/kingdom/council/council.py:155`).

Also, chat is not loading branch resume IDs (`src/kingdom/tui/app.py:162`), but it still keeps its own in-memory session continuity because `CouncilMember` always uses `self.session_id` in commands (`src/kingdom/council/base.py:88`) and updates it on responses.

1. Right isolation boundary
Use a lane boundary: `(workflow_type, scope_id, agent)`.

- `chat` lane scoped by `thread_id`
- `council ask` lane scoped by `thread_id` (or explicit run/thread)
- `peasant` lane scoped by `session_name`/ticket

And split concepts:
- Operational state: status/pid/last_activity (branch-level)
- Resume context: lane-scoped resume IDs (not shared globally)

2. Should chat sessions persist?
Recommend `chat = no resume` (fresh each query) by default.
Reason: chat already uses full thread-history injection; hidden resume context creates non-determinism and cross-talk risk. If ever needed later, make thread-scoped chat resume opt-in.

3. Chat open + `kd council ask` in another terminal
They should share only explicit thread messages, not hidden resume state.
So: same thread can share visible conversation via files, but backend resume lineages remain isolated per lane.

4. Edge cases / failure modes to handle
- Concurrent writes to same lane file
- Two chat UIs on same thread
- Thread rename/delete with stale lane pointers
- Model/backend change invalidating old resume IDs
- Crash mid-write or partial JSON
- Migration from legacy per-agent `resume_id` without losing active flows
- Debug confusion when operational state and resume state diverge

Simplest implementation path
1. Add lane-aware resume API in `session.py` (`get/set_resume_id(lane, agent)`).
2. Keep existing branch-level operational state updates for pid/status.
3. Update council/harness loaders/savers to use lane-specific resume APIs.
4. For chat, force `session_id=None` behavior and never persist resume.
5. Add a deterministic concurrent test (chat + non-chat) for `0f27` proving zero cross-lane contamination.
