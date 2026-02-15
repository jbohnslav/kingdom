---
from: codex
to: king
timestamp: 2026-02-15T11:56:18Z
---

I’ll review this as a code-review pass: I’m going to inspect the updated files directly (`agent.py`, council paths, and tests) and then return findings ordered by severity with concrete file references.
I’ve verified the updated code paths. I’ll run the focused test files next to validate assumptions and catch regressions that aren’t obvious from the diff alone.
1. **[High] Claude NDJSON parser/extractor does not match the event shape documented in your design, so streamed text can be lost.**
`parse_claude_response` and `extract_claude_stream_text` only handle top-level `{"type":"content_block_delta", ...}` (`src/kingdom/agent.py:140`, `src/kingdom/agent.py:438`).
Your design’s example uses wrapped events: `{"type":"stream_event","event":{"type":"content_block_delta",...}}` (`.kd/branches/council-improvements/design.md:37`).
With that shape, parser returns empty text and only maybe a session id. That can flow into `*Error: None*` message bodies (`src/kingdom/council/council.py:125`).

2. **[High] NDJSON detection by line count is brittle and drops valid one-line stream events.**
Both parsers branch on `len(lines) <= 1` to “single JSON mode” (`src/kingdom/agent.py:115`, `src/kingdom/agent.py:201`).
A valid one-line NDJSON event (for example a lone delta/result line) gets parsed as legacy JSON and returns empty text for delta-shaped events.
This is a real edge case for short outputs and partial captures.

3. **[Medium] Cursor parsing is still speculative and may miss real stream-json structures.**
`parse_cursor_response` and `extract_cursor_stream_text` assume top-level `content_block_delta` or `assistant.text` (`src/kingdom/agent.py:226`, `src/kingdom/agent.py:474`).
Your design explicitly says Cursor token-level behavior is unconfirmed (`.kd/branches/council-improvements/design.md:151`).
Risk: “works in tests, fails in live CLI output.”

4. **[Medium] `--include-partial-messages` is hard-enabled for Claude streaming with no compatibility fallback.**
It is always appended when `streaming=True` (`src/kingdom/agent.py:277`).
If a user has a Claude CLI version without that flag, council queries can fail outright instead of degrading to non-partial streaming.

5. **[Low] Comment drift after `.md -> .jsonl` rename.**
`council.py` comment still says `.stream-{member}.md` (`src/kingdom/council/council.py:111`) while code writes `.jsonl` (`src/kingdom/council/council.py:112`).

**What looks good**
1. Streaming flag threading is clean and minimal: `build_command(..., streaming=True)` on council path only (`src/kingdom/council/base.py:65`), defaults preserve non-council behavior (`src/kingdom/agent.py:389`).
2. `.stream-*.jsonl` rename is consistently applied in both sync and async worker paths (`src/kingdom/council/council.py:112`, `src/kingdom/council/worker.py:52`).
3. Extractor API shape is good for reuse (`src/kingdom/agent.py:488`).

**Test signal**
I ran:
- `uv run pytest tests/test_agent.py tests/test_council.py -q`
- `uv run pytest tests/test_cli_council.py -q`
All passed.
Main concern is fixture realism: new tests don’t include the wrapped `stream_event` shape shown in your design.

**Recommendation**
Ticket is close, but I would not call it complete yet due to finding #1 and #2. These are correctness blockers for real streaming UX.
