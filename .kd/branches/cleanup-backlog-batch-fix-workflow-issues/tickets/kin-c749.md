---
id: kin-c749
status: closed
deps: []
links: []
created: 2026-02-13T18:06:55Z
type: bug
priority: 1
---
# Council watch vs --to mismatch

council_watch derives expected_members from thread metadata, not current ask target. --to <member> blocks until timeout waiting for all original members. Fix: pass expected members from current ask scope. (cli.py:594, #5/#15 from PR #6 review)
