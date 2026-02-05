---
id: kin-a321
status: open
deps: []
links: []
created: 2026-02-05T01:13:15Z
type: bug
priority: 2
---
# kd done timing creates awkward git workflow

Running kd done at end of PR review is awkward because it moves tickets to archive, creating uncommitted git changes after the PR is already merged. But running it before merge risks archiving a branch while its PR is still open.

Possible solutions:
1. Add a --no-archive flag to kd done that just clears current without moving files
2. Have kd done only move files if there are no uncommitted changes on the branch
3. Rethink whether ticket files should move at all - maybe archive is just a state, not a directory
