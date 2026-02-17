---
from: codex
to: king
timestamp: 2026-02-17T03:59:37Z
---

This looks coherent and technically defensible.

- You cleanly separated two concerns: `cursor` as a supported backend vs `cursor` as an auto-provisioned council member.
- Keeping `DEFAULT_AGENTS["cursor"]` removed while restoring parser/builder/validation paths is the right shape for “not default, still supported.”
- Keeping `merge_assistant_snapshots()` removed and standardizing on concat in `poll.py` is a good simplification, as long as all tests now assert concat semantics (which your summary says they do).

Two risks I’d still keep an eye on:

- Any code path that infers “supported backend” from `DEFAULT_AGENTS` instead of `VALID_BACKENDS` could still behave inconsistently.
- Existing threads created under old merge behavior could show slightly different transcript shape when re-polled; not necessarily wrong, but worth acknowledging if users notice.

Net: this aligns with ticket intent (`remove as council member`, not `delete backend support`) and avoids reintroducing prior complexity.
