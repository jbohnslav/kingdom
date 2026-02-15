---
from: cursor
to: king
timestamp: 2026-02-15T11:54:26Z
---

This implementation of `e756` is robust and well-structured. It correctly addresses the core requirement of enabling streaming JSON output for Council queries while maintaining backward compatibility for other agent interactions.

### Strengths

1.  **Hybrid Parsing Strategy:** The decision to auto-detect single-line (JSON) vs. multi-line (NDJSON) in `parse_claude_response` and `parse_cursor_response` is excellent. It avoids breaking existing "peasant" workflows that rely on the simpler format while seamlessly supporting the new streaming mode.
2.  **Clean Abstraction:** `extract_stream_text` provides a unified interface for the TUI/Watch command to consume streams without needing to know backend specifics. This decoupling is crucial for the Phase 2 TUI work.
3.  **Correct CLI Flags:** You correctly identified the need for `--verbose` and `--include-partial-messages` for Claude to emit token-level deltas, which is a common pitfall.
4.  **Test Coverage:** The added tests cover the critical paths: NDJSON parsing, fallback to result text, ignoring non-text events, and handling invalid JSON.

### Minor Issues / Edge Cases

1.  **Codex Command Builder:**
    *   *Observation:* `build_codex_command` accepts `streaming=True` but ignores it.
    *   *Risk:* Minimal. Codex defaults to streaming JSONL anyway.
    *   *Suggestion:* Explicitly document in the docstring that Codex is "always streaming" to avoid future confusion.

2.  **Cursor Parsing Ambiguity:**
    *   *Observation:* In `parse_cursor_response`, you check for `assistant` event type *or* `content_block_delta`.
    *   *Risk:* If Cursor emits *both* (e.g., a delta stream followed by a final "assistant" summary block), you might duplicate the text.
    *   *Fix:* Ensure that if you are accumulating `text_delta` events, you ignore the final `assistant` block if it's just a concatenation of the deltas. However, since `text_parts` is a list, appending the final block would indeed duplicate it.
    *   *Recommendation:* In `parse_cursor_response`, if `text_parts` is already populated from deltas, skip the `assistant` block or `result` text.

3.  **Empty Line Handling:**
    *   *Observation:* `lines = [ln for ln in stdout.strip().split("\n") if ln.strip()]`.
    *   *Risk:* If the output is truly empty (e.g., process crash before any output), `lines` is empty. The code falls through to `return "".join(text_parts), session_id, raw` which returns `("", None, raw)`. This is correct behavior (silent failure handled by the caller), but worth noting.

### Specific Code Review

**`src/kingdom/agent.py`**

```python
# In parse_claude_response and parse_cursor_response

        elif event_type == "result":
            session_id = event.get("session_id")
            # result event also carries the final text
            result_text = event.get("result")
            if result_text and not text_parts:  # <--- GOOD: Prevents duplication
                text_parts.append(result_text)
```

You *did* handle the duplication case for the `result` event, but check `parse_cursor_response` for the `assistant` event:

```python
# In parse_cursor_response

        elif event_type == "assistant":
            text = event.get("text", "")
            if text:
                text_parts.append(text)  # <--- POTENTIAL DUPLICATION
```

If Cursor emits deltas AND an `assistant` event, this will duplicate text. I recommend adding `and not text_parts` here as well, similar to the `result` block.

### Recommendation

The code is **approved** with one small suggestion:

*   **Fix:** In `parse_cursor_response`, change `if text:` to `if text and not text_parts:` to prevent potential duplication if Cursor emits both deltas and a final summary event.

Otherwise, this is a solid implementation that lays the groundwork for the TUI. You can proceed to merge.
