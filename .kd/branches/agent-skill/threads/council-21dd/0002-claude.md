---
from: claude
to: king
timestamp: 2026-02-14T01:59:50Z
---

Great analysis. Here's what I found:

## Current State of Streaming/Intermediate Capture

**There is no streaming-to-file currently.** The system is entirely batch-oriented:

1. **`subprocess.run(capture_output=True, timeout=300)`** in `council/base.py:69` — blocks until the process exits, then reads stdout/stderr all at once.

2. **On timeout, everything is lost** — `council/base.py:96-107` catches `TimeoutExpired`, sets `text=""` and `error="Timeout after Xs"`. The subprocess buffers are discarded by Python. No partial output is captured whatsoever.

3. **Thread messages are written only after completion** — `thread.py:218` writes the `NNNN-sender.md` file after the full response is parsed.

4. **Session IDs do survive** — so the *conversation context* on the LLM side is preserved, but the actual *response text* that was being generated is gone.

## The One Exception: Peasant Worktrees

Peasant worktree mode (`cli.py:1102-1115`) does redirect stdout/stderr to file descriptors at spawn time, so the harness logging streams to disk. But the individual agent responses within the harness loop are still captured batch-style (`harness.py:351`).

## What Would Need to Change for "Continue Where You Left Off"

To get the behavior you're describing, you'd need two things:

1. **Stream capture during execution** — Switch from `subprocess.run(capture_output=True)` to `subprocess.Popen()` with stdout piped, then read line-by-line and tee to a file as bytes arrive. This way, even if the process times out, whatever was written to the file is preserved.

2. **Resume logic** — On timeout (or restart), detect the partial response file, include it in the next prompt as context ("here's what you said so far, continue from where you left off"), and append the continuation to the same thread message.

The timeout bump to 10 minutes is a one-liner in `base.py` (the default is 300s). The streaming piece is more involved but not architecturally disruptive — it's mainly replacing `subprocess.run()` with a `Popen` + read loop + tee pattern in `CouncilMember.query()`.

Want me to sketch out a more concrete implementation plan for the streaming/resume logic, or is this enough context for the ticket?
