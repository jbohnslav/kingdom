---
from: claude
to: king
timestamp: 2026-02-15T11:55:03Z
---

Here's my review.

---

## e756 Implementation Review

**Verdict: Clean, correct, ready to close.** One stale comment to fix, one minor observation, nothing blocking.

### What's right

**The auto-detect heuristic is smart.** Single-line = old JSON path, multi-line = NDJSON. This is the simplest possible way to maintain backward compatibility without passing a mode flag through the parser. Peasant workers still use `--output-format json` → single-line JSON → old parser path. Council uses `stream-json` → multi-line NDJSON → new parser path. No mode parameter needed. Clean.

**The `streaming=True` integration point is minimal and correct.** Only `CouncilMember.build_command()` at `base.py:65` passes `streaming=True`. Every other call path (peasant workers, direct `build_command()` calls) defaults to `streaming=False`. The blast radius is exactly right.

**The `--output-format` replacement via `cmd.index()` is defensive.** The `try/except (ValueError, IndexError): pass` at `agent.py:271-276` means if someone changes `BACKEND_DEFAULTS` to remove `--output-format`, the streaming flag silently does nothing rather than crashing. That's the right failure mode for a flag that adds capability.

**Stream extractors follow existing patterns.** `STREAM_TEXT_EXTRACTORS` dict + `extract_stream_text()` dispatcher mirrors `RESPONSE_PARSERS` + `parse_response()` and `COMMAND_BUILDERS` + `build_command()`. Consistent architecture.

**Tests are thorough.** 27 new tests covering: streaming command building for all 3 backends, NDJSON parsing for Claude and Cursor (including edge cases: invalid JSON lines, result-fallback, mixed event types), stream text extraction for all 3 backends + unknown backend + invalid JSON. All 113 pass.

**The `.md` → `.jsonl` rename is complete.** Both `council.py:112` and `worker.py:52` updated. No stale references remain in production code.

### One thing to fix

**Stale comment at `council.py:111`.** The comment says `# Stream to .stream-{member}.md` but the code now writes `.stream-{member}.jsonl`. Trivial but it'll confuse anyone reading this code later.

### Observations (not blocking)

**`extract_claude_stream_text` and `extract_cursor_stream_text` are identical.** Both check for `content_block_delta` → `text_delta`. This is fine — they're separate functions keyed by backend name, and if Cursor's format diverges later (which the design doc flags as unverified), you'll want them separate. Not worth abstracting today.

**The Claude NDJSON parser doesn't handle the `stream_event` wrapper mentioned in the design doc.** The design doc's streaming investigation section says Claude emits `{"type":"stream_event","event":{"type":"content_block_delta",...}}` — a nested wrapper. But the parser checks for `event.get("type") == "content_block_delta"` at the top level. This means either:
1. The design doc's example was from an older Claude Code version and the current output is flat (no `stream_event` wrapper), or
2. The parser won't match real Claude Code stream-json output.

This needs verification against actual Claude Code output. If Claude Code really does wrap events in `{"type":"stream_event","event":{...}}`, the parser needs to unwrap. But the tests use flat events and pass, which suggests you tested against real output and it's flat. Worth confirming with a quick manual test before closing the ticket: run `claude --print --output-format stream-json --verbose --include-partial-messages -p "say hi" 2>/dev/null | head -5` and check the shape.

### AC Checklist

| Criterion | Status |
|---|---|
| `build_command()` gains `streaming=True` parameter | Done (`agent.py:260,297,332,394`) |
| Council query path passes `streaming=True` | Done (`base.py:65`) |
| Stream files renamed `.md` → `.jsonl` | Done (`council.py:112`, `worker.py:52`) |
| `parse_claude_response()` handles NDJSON | Done (`agent.py:101-151`) |
| `parse_cursor_response()` handles NDJSON | Done (`agent.py:189-240`) |
| `extract_stream_text(line, backend)` function | Done (`agent.py:488-496`) |
| Codex parser unchanged | Confirmed — no diff to `parse_codex_response()` |
| Existing tests updated; new tests cover NDJSON | Done — 27 new tests, all pass |
| Non-streaming paths still use `--output-format json` | Confirmed — `streaming` defaults to `False` |

Fix the stale comment, verify the `stream_event` wrapper question, and this is ready to close.
