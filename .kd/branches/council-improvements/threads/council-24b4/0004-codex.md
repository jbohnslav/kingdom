---
from: codex
to: king
timestamp: 2026-02-15T14:18:32Z
---

I’ll make a concrete recommendation among the three options, but first I’m quickly confirming whether the thread parser already tolerates extra frontmatter keys so we can judge option 2 implementation risk accurately.
Parser check complete: next I’m reading `parse_frontmatter` itself to confirm unknown keys behavior and whether option 2 is backward-compatible with current readers.
Choose **Option 2**.

It fixes the real bug without coupling machine logic to markdown presentation, and it is low-risk with current parsing.

Why:

1. **Correctness**
`retry` currently infers failure from body prefixes (`src/kingdom/cli.py:968`), which is brittle and misses timed-out partials because `thread_body()` prefers text (`src/kingdom/council/base.py:26`). Metadata is the right place for completion/error state.

2. **Robustness**
Option 1 still encodes state in rendered text and keeps retry dependent on formatting conventions (`*Error:`). That is fragile long-term and easy to regress.

3. **Compatibility**
Thread frontmatter parsing already tolerates extra keys (`src/kingdom/parsing.py:88`), so adding fields is backward-compatible for readers that ignore unknown fields.

4. **Option 3 is not acceptable**
This is a real correctness defect, not a cosmetic edge case. It can silently suppress retries after failed responses.

Recommended shape (minimal, not over-designed):

1. Add frontmatter status fields on assistant messages: `error` (string or null) and `complete` (bool).
2. Mark timed-out partials as `complete: false`, `error: "Timeout after ..."` while keeping body as partial text.
3. Make retry logic use metadata first; keep current body-prefix detection only as fallback for legacy messages.
4. Update watch/show rendering to surface metadata error state so humans see “partial + timeout” clearly.

Tests to require before merge:

1. Retry after timeout+partial text should re-query.
2. Retry after clean full response should not re-query.
3. Legacy thread with `*Error:` body and no metadata should still retry.
4. Mixed thread (some metadata, some legacy) should behave deterministically.
