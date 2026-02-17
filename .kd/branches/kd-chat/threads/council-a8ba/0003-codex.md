---
from: codex
to: king
timestamp: 2026-02-15T18:57:38Z
---

I’ll review the current `kd design` document and assess whether it supports your end-goal: a persistent, group-chat-style TUI with councillors. First I’m loading the kingdom skill guidance and then I’ll read the design doc plus any linked context files.
I’ve loaded the skill guidance; next I’m pulling the current branch status and the design document content so I can critique the plan directly.
I have the design doc and will now sanity-check it against the current code paths (thread storage, streaming files, council execution, config schema) so the feedback is grounded in what already exists versus assumptions.
I’m now drilling into the actual council/watch implementation to verify where the design matches current behavior and where it assumes capabilities that don’t exist yet (especially for `kd chat`, stream lifecycle, and config semantics).
I’ve found several concrete mismatches between the doc and current code; I’m verifying session/thread scoping now because that’s a major design risk for “persistent group chat” behavior.
I’ve completed the code-grounded review and the doc is directionally solid for Phase 1, but there are several high-impact gaps for true persistent group-chat behavior (session scoping, round semantics, and failure/state modeling). I’ll give you a severity-ordered review with concrete decisions to lock before ticket breakdown.
**Verdict**
Directionally good for Phase 1, but not yet a complete/safe plan for “persistent group chat with my best engineers.”

**Findings (ordered by severity)**
1. `council.chat` / `council.auto_commit` are documented as existing, but they do not exist in schema today.
` .kd/branches/kd-chat/design.md:30`, `src/kingdom/config.py:98`, `src/kingdom/config.py:176`
This will fail config validation if implemented per doc without schema work first.

2. Session continuity is currently scoped per `branch + member`, not per thread, which risks cross-thread context bleed.
`src/kingdom/session.py:53`, `src/kingdom/session.py:68`, `src/kingdom/cli.py:375`
For persistent chat, this is a core correctness decision.

3. The doc says stream-file disappearance means “message finalized,” but current behavior also deletes/recreates stream files during retries.
` .kd/branches/kd-chat/design.md:49`, `src/kingdom/council/base.py:123`, `src/kingdom/council/base.py:131`, `src/kingdom/cli.py:997`
TUI state logic based on deletion alone will be wrong.

4. Current status/watch model assumes rounds are anchored to the latest **king** message only, which does not fit member-to-member auto-turns.
`src/kingdom/thread.py:370`, `src/kingdom/thread.py:389`, `src/kingdom/cli.py:945`
Group-chat mode needs explicit round/turn metadata or equivalent persisted markers.

5. Partial-timeout responses can be persisted as plain text (without error marker), so retries/status may misclassify failures as success.
`src/kingdom/council/base.py:29`, `src/kingdom/council/base.py:34`, `src/kingdom/thread.py:409`
This is especially risky for unattended auto-rounds.

6. Command/dependency rollout is under-specified: no `kd chat` command exists yet, and Textual is not present in project deps.
` .kd/branches/kd-chat/design.md:81`, `pyproject.toml:7`

7. “Resume current or new” is not enough for persistent UX; explicit thread selection/switching is missing (`kd chat <thread-id>` / picker behavior).
` .kd/branches/kd-chat/design.md:37`

**Key decisions to lock up front**
1. Session scope: per-thread vs per-branch resume IDs (recommend per-thread for chat correctness).
2. Round model: persist explicit round/turn metadata vs infer from message ordering.
3. Stream lifecycle contract: what definitively means “done” (message file write, not stream deletion).
4. Failure semantics in thread files: preserve timeout/error metadata even with partial text.
5. Chat thread selection UX: current thread only vs explicit thread open/switch/list.
6. Auto-mode scheduler contract: behavior on failure, retry policy, and user interrupts with queued inputs.
7. Backward compatibility boundary: how `kd council show/status/watch/retry` should interpret group-chat threads.

If you want, I can turn this into a concrete “design v2 checklist” you can paste directly into `kd design` before breakdown.
