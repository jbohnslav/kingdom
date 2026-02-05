---
id: kin-a007
status: closed
deps: [kin-9758]
links: []
created: 2026-02-04T02:47:41Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# kd council ask with Rich output

Refactor council command to 'council ask' with Rich terminal output. No auto-synthesis — King reads responses directly.

## Acceptance Criteria

- kd council ask 'prompt' queries all council members in parallel
- Terminal output uses Rich panels (top-to-bottom, one per model)
- Rich Markdown rendering inside panels (syntax highlighting for code blocks)
- Progress/spinner shows which models are still running
- --json flag returns machine-readable output (responses, paths, no synthesis field)
- --open flag opens response directory in $EDITOR after saving
- --timeout flag sets per-model timeout (default 120s)
- Responses saved to run bundle (see kin-9758)
