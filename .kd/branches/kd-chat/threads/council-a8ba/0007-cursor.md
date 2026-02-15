---
from: cursor
to: king
timestamp: 2026-02-15T19:38:08Z
---

The updated design document is much stronger and addresses the key feedback points well. The decision to use **thread history injection** instead of session resume for group chat is the right call for ensuring cross-agent awareness, even if it risks losing some ephemeral tool context.

I have just two final observations to ensure the implementation goes smoothly:

### 1. PID Tracking Gap
You correctly identified that `AgentState` has a `pid` field, and you plan to use it for cancellation (Decision #269). However, `CouncilMember.query_once` currently **does not write the PID** to `AgentState`.
*   **Correction:** You must update `CouncilMember.query_once` (or the new async query path) to explicitly call `update_agent_state(..., pid=process.pid)` immediately after `subprocess.Popen`. Without this, the TUI will have no way to look up and kill the background processes when the user hits Escape.

### 2. Config Schema Updates
You noted adding `chat` keys to `VALID_COUNCIL_KEYS`. Don't forget that **Phase 3** adds `council.preamble`.
*   **Reminder:** Add `preamble` to `VALID_COUNCIL_KEYS` in `src/kingdom/config.py` as well, or the config validation will reject your new customizable preamble.

### Final Verdict
The design is **approved**. It provides a clear, implementable path for a high-quality TUI chat experience. You can proceed with the implementation.
