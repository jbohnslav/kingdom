---
from: codex
to: king
timestamp: 2026-02-17T12:51:27Z
---

Strong set. I’d add 3, skip the rest at top-level README.

Add as new `Why` bullets:
- **Independent first-pass opinions**: council members answer independently by default, which reduces anchoring/groupthink and gives genuinely different takes.
- **Session continuity**: follow-ups reuse member context, so iteration is faster/cheaper than restarting prompts every turn.
- **Worklog audit trail**: ticket worklogs capture decisions, failures, and test results in git, so you can review *why* changes happened.

Keep out of top `Why` (move to architecture/docs):
- Atomic claiming (too implementation-detail heavy)
- `kd peasant review` quality gates (better in workflow section)
- No server/database + vendor flexibility (already implied by markdown/file-based framing; can be one sentence elsewhere)

If you want, I can rewrite the `Why` section to a tight 6 bullets that combines current + these 3 without feeling long.
