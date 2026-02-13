---
id: kin-09c9
status: closed
deps: []
links: []
created: 2026-02-13T14:03:53Z
type: task
priority: 2
---
# @ mentions to tag council members inline

Currently you have to use `kd council ask --to claude "question"` to talk to a specific council member, which is clunky. Want a way to @mention council members from the command line — something like `kd @claude "what do you think about this?"` or `kd council ask "@claude @codex weigh in on caching"`. Could also work as a shorthand so you don't have to remember the full `council ask --to` syntax. Need to figure out the right UX — could be a top-level `@` command, parsing @mentions from the prompt string, or something else entirely.

## Acceptance Criteria

- [ ] Can tag one or more council members by name from the CLI
- [ ] Shorter/more natural than `kd council ask --to <name>`
- [ ] Works within the existing thread model (messages go to the right thread)
