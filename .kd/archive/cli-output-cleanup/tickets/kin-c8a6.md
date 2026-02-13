---
id: kin-c8a6
status: closed
deps: []
links: []
created: 2026-02-09T17:09:00Z
type: task
priority: 2
---
# Remove Rich panels from CLI output

Rich panels (bordered boxes with `╭──╮` etc.) add unnecessary formatting, weird line breaks, and visual noise. They make output harder to parse for agents and harder to copy-paste for humans. Replace with simple `typer.echo` / plain text output everywhere — council responses, peasant read, peasant logs, peasant review, etc.

## Acceptance Criteria

- [ ] No Rich Panel usage in CLI output
- [ ] Output is plain text, easy to copy-paste and parse by agents
- [ ] Rich tables (e.g. `kd peasant status`) are fine — only panels need to go
