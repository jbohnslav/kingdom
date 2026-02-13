---
id: kin-8af4
status: open
deps: []
links: []
created: 2026-02-13T18:07:12Z
type: bug
priority: 2
---
# Watch timeout buffer for council

council_watch uses same timeout as worker. Member finishing at boundary can be missed. Add ~30s buffer to watch timeout. (cli.py:627, #10 from PR #6 review)
