---
id: kin-3dd3
status: open
deps: []
links: []
created: 2026-02-13T13:03:21Z
type: task
priority: 2
---
# CLI output should use markdown not Rich panels

Rich panels (bordered boxes with `╭──╮`) add visual noise and break copy-paste. Replace with plain markdown output that renders well in terminals with colored markdown support. Use Rich's `Markdown` renderer instead of `Panel` so output is clean text with ANSI colors — headers, bold, code blocks etc. all render correctly without box-drawing characters.

## Acceptance Criteria

- [ ] No `Panel` usage in CLI output (council responses, peasant read, peasant logs, peasant review, etc.)
- [ ] Output uses Rich `Markdown` rendering so colored markdown works in terminals
- [ ] Rich tables (e.g. `kd peasant status`) are fine — only panels need to go
- [ ] Output is easy to copy-paste and parseable by agents
