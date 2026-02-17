---
from: claude
to: king
timestamp: 2026-02-15T19:38:08Z
---



Let me re-read the updated design doc.This is a much stronger doc. You addressed the big gaps — layout wireframe, widget tree, module structure, input handling, error display, thread resumption, interop with `kd council ask`, and the history injection format. Let me give you the remaining issues.

## What Improved

The "What does NOT exist yet" section is a great addition — it prevents someone from assuming infrastructure is already in place. The TUI Architecture section with the wireframe and widget tree is exactly what was needed. The Phase 3 (configurable preamble) is a clean separation. The interop section between `kd chat` and `kd council ask` is thorough and correct.

## Remaining Issues

### 1. `council.chat` config nesting needs a structural decision

Line 132-136: You describe `council.chat.auto_rounds` and `council.chat.mode` as nested under `council.chat`, but the current `CouncilConfig` dataclass is flat and `VALID_COUNCIL_KEYS` is a flat set. You say "add these to `VALID_COUNCIL_KEYS`" — but `chat` would be a nested object, not a scalar key. You need to decide: is it `council.chat.auto_rounds` (nested object requiring a new `ChatConfig` dataclass and nested validation), or `council.auto_rounds` / `council.mode` (flat, simpler, matches existing pattern)? I'd recommend flat — it matches the existing council/peasant config style and avoids the nested validation complexity for two keys.

### 2. Phase 1 query path is underspecified

In Phase 1, when the user types a message and hits Enter, what happens? The doc describes the streaming display and the async bridge, but doesn't spell out the actual query flow:

- Does the TUI create `CouncilMember` instances directly? Or does it shell out to `kd council ask --async` and then watch?
- If it creates members directly, it needs to replicate the setup logic from `council_ask()` — loading config, resolving agents, loading sessions, creating/resuming threads, writing the king message, etc.
- If it shells out to the existing CLI, it gets all that for free but loses fine-grained subprocess control (the cancellation problem).

The most natural approach is: the TUI manages `Council` and `CouncilMember` instances directly (via `Council.create()`), uses `asyncio.to_thread()` to call `member.query()`, and writes thread messages itself. This reuses the existing orchestration but gives the TUI subprocess handles for cancellation. The doc should state this explicitly.

### 3. Auto-scroll behavior is unspecified

When a streaming panel is growing, should the message log auto-scroll to follow it? What if the user has scrolled up to re-read an earlier message — does new content pull them back down? Standard chat UX is: auto-scroll if the user is at the bottom, don't if they've scrolled up. Worth a one-liner in the doc since it affects the `MessageLog` widget implementation.

### 4. The "waiting..." panels have a lifecycle gap

The wireframe shows `waiting...` panels for codex and cursor while claude is streaming. But when does a `WaitingPanel` get created? Two scenarios:

- **Parallel first round (broadcast mode)**: All members are queried at once. You'd create `WaitingPanel` for all members immediately, then upgrade to `StreamingPanel` as stream files appear. This works.
- **Sequential auto-turn**: Only one member is queried at a time. Do you show a `WaitingPanel` for the *next* member in the round? Or nothing until their turn starts? Showing it preemptively tells the user "more is coming" which is nice UX.

Minor, but worth clarifying so the widget lifecycle is unambiguous during implementation.

### 5. Open question on session resume should be closed

Line 280: You're "leaning toward thread-history-only." I think you should just decide. The argument is clear — session resume carries tool-use context but duplicates the agent's own messages and doesn't provide cross-agent awareness. In the council advisory role (read-only, no tool use that matters across turns), tool-use context is near-zero value. Thread history only. Close it.

### 6. Subprocess cancellation should also be closed

Line 281: Three options listed, leaning nowhere. Looking at the code, option (a) — store the `Popen` handle on the `CouncilMember` — is the cleanest. It's a one-field addition (`self.process: subprocess.Popen | None = None`) set inside `query_once()`, and the TUI calls `member.process.terminate()` on Escape. Option (b) using `AgentState.pid` is messier because it requires reading/writing JSON files and introduces a race between PID write and PID read. Option (c) is over-engineering. Just go with (a).

### 7. Missing: what `kd chat` does when no agents are installed

The doc handles "textual not installed" (show install hint). But what about when the user has textual but no agent CLIs are available? `CouncilMember.query_once()` raises `FileNotFoundError` which becomes an error response. In the TUI, this would show as an error panel per member. That's probably fine, but worth a sentence confirming that agent availability errors are handled by the standard error panel path, not a separate pre-flight check.

### 8. Phase 2 round-robin order isn't defined

Round-robin "each member responds once per round" — but in what order? The order in `council.members` from config? Alphabetical? The doc should state this. I'd recommend config order (`council.members` list), since the user can control it.

### 9. Minor: line 37 mentions `council.auto_commit` but it's never defined

The "What does NOT exist yet" section mentions `council.auto_commit` as a config key that doesn't exist. But nowhere in the design doc is `auto_commit` specified as a feature. Either define what it does or remove the mention.

## Summary

The doc is ready for breakdown after closing those open questions (session resume: drop it; subprocess cancellation: store handle on member; config nesting: go flat) and adding the small clarifications (query path, auto-scroll, round-robin order, auto_commit reference). None of these require rethinking the architecture — they're just tightening the spec so ticket implementation is unambiguous.
