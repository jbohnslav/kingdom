---
from: codex
to: king
timestamp: 2026-02-16T12:09:55Z
---

codex: Cursor covered three points about `213e` prompt history formatting:

1. The `codex: codex:` duplication issue and recommendation to strip leading `Name:` prefixes from agent outputs before persisting.
2. The risk of meta/error text polluting future history, and suggestion to treat errors explicitly (for example `[cursor timed out]`) instead of raw error prose.
3. Directed message formatting (`king (to cursor): ...`) as good and worth keeping.

Main takeaway from Cursor: the format is mostly good, but output sanitization and error-history policy need explicit handling.
