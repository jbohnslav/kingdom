---
id: kin-d49a
status: closed
deps: []
links: []
created: 2026-02-13T18:06:55Z
type: bug
priority: 2
---
# Parallel --hand workers on same checkout

Existing-process guard only checks current ticket session. Two --hand workers for different tickets can run against the same working tree, interleaving edits. Block or warn when a second --hand worker launches. (cli.py:1099, #6 from PR #6 review)
