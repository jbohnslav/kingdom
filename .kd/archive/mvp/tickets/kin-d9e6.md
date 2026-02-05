---
id: kin-d9e6
status: closed
deps: []
links: []
created: 2026-02-04T23:19:46Z
type: task
priority: 2
---
# Fix hardcoded council member iteration

cli.py:733 _display_rich_panels() iterates over hardcoded ['claude', 'codex', 'agent'] list. Replace with responses.keys() or council.members for maintainability.
