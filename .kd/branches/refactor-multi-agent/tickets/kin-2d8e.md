---
id: kin-2d8e
status: open
deps: []
links: []
created: 2026-02-07T22:33:57Z
type: task
priority: 1
---
# Agent session state

Per-agent runtime state in sessions/<agent>.json. Each agent writes only its own file (no locking needed). Helpers to get/set agent status, resume_id, pid, ticket, thread, timestamps. Agent status enum: idle, working, blocked, done, failed, stopped. Branch-level current_thread stays in state.json. Migrate existing .session files (plain text resume IDs) to the new .json format on first access.

## Acceptance
- [ ] get_agent_state(branch, agent_name) reads sessions/<agent>.json
- [ ] set_agent_state(branch, agent_name, **fields) writes sessions/<agent>.json
- [ ] list_active_agents(branch) scans sessions/ for agents with status != idle
- [ ] get_current_thread(branch) / set_current_thread(branch, thread_id) manage current thread pointer in state.json
- [ ] Existing .session files migrated to .json on first read (read old format, write new format, remove old file)
- [ ] Existing state.json fields preserved
