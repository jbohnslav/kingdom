---
id: kin-304a
status: open
deps: []
links: []
created: 2026-02-07T22:33:49Z
type: task
priority: 1
---
# Agent config model

Parse agent definition .md files from .kd/agents/. Markdown with YAML frontmatter (name, backend, cli, resume_flag). Replace hardcoded ClaudeMember/CodexMember/CursorAgentMember classes with a single config-driven Agent class that builds commands from the config. Keep the existing CouncilMember.parse_response() logic as backend-specific parsers. Create default agent files on kd init.

## Acceptance
- [ ] load_agent(name) reads .kd/agents/<name>.md and returns config
- [ ] list_agents() returns all registered agents
- [ ] Agent config drives command building (replaces hardcoded CLI strings)
- [ ] Backend-specific response parsing preserved (claude JSON, codex JSONL, cursor JSON)
- [ ] kd init creates default agent files for claude, codex, cursor
- [ ] kd doctor checks agent CLIs based on config
