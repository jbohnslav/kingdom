---
from: claude
to: king
timestamp: 2026-02-15T14:18:30Z
---

Good question. Let me check how the thread message format works to understand what option 2 would actually entail.**Recommendation: Option 3 — leave it as-is.**

Here's my reasoning:

**The scenario is narrow.** For a partial-timeout response to escape detection:
1. The auto-retry in `query()` must have been exhausted — and now with timeouts as non-retriable, it won't even retry timeouts (which is correct; if the model is slow, retrying just wastes more time)
2. The agent must have produced meaningful partial text before being killed
3. The user then runs `kd council retry` expecting it to re-query that member

In that case, the user already *knows* the response timed out — they saw the timeout in the watch output or the `*Error:` rendering. They can manually re-ask or reset+ask.

**Option 1 is lossy and ugly.** Prefixing a 500-word partial response with `*Error: Timeout*` means the error marker is in-band with the content. When someone reads the thread later (or another agent consumes it), the partial text is polluted. And if you strip the prefix for display, you're back to parsing conventions.

**Option 2 is the "right" answer but it's over-engineering for now.** Adding an `error` field to the message frontmatter means:
- Changing `add_message()` signature (new optional `error` param)
- Updating `parse_message()` to read it
- Adding `error` to the `Message` dataclass
- Updating `council_retry` to check `msg.error` instead of string prefix matching
- Every existing thread on disk has no `error` field, so you need backwards compat

That's a real schema change to handle a case that auto-retry already mostly covers. It's the right direction if you're going to build more sophisticated thread semantics (reactions, status, edits), but as a fix for this one edge case it fails the "is this a real problem or imaginary?" test from CLAUDE.md.

**What I would do:** Keep option 3, but add a one-line comment in `thread_body()` acknowledging the tradeoff:

```python
# Note: partial timeout responses (text + error) return just the text.
# This means retry won't detect them as failures. Acceptable because
# auto-retry already handles immediate retries, and timeouts are now
# non-retriable.
```

That way the next person who looks at this code understands it was a deliberate decision, not an oversight.
