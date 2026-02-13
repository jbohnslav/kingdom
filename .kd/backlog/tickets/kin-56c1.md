---
id: kin-56c1
status: open
deps: []
links: []
created: 2026-02-13T18:07:12Z
type: bug
priority: 2
---
# EDITOR with flags breaks ticket edit

Ticket edit runs [editor, file] where editor is from EDITOR env var. Fails if EDITOR includes flags like 'code --wait'. Use shlex.split(editor). (cli.py:2331-2346, #12 from PR #6 review)
