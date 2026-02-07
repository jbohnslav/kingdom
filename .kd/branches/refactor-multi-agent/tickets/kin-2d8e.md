---
id: kin-2d8e
status: closed
deps: []
links: []
created: 2026-02-07T22:33:57Z
type: task
priority: 1
---
# Agent session state

Per-agent runtime state in sessions/<agent>.json. Each agent writes only its own file (no locking needed). Helpers to get/set agent status, resume_id, pid, ticket, thread, timestamps. Agent status enum: idle, working, blocked, done, failed, stopped. Branch-level current_thread stays in state.json. Migrate existing .session files (plain text resume IDs) to the new .json format on first access.

## Acceptance
- [x] get_agent_state(branch, agent_name) reads sessions/<agent>.json
- [x] set_agent_state(branch, agent_name, **fields) writes sessions/<agent>.json
- [x] list_active_agents(branch) scans sessions/ for agents with status != idle
- [x] get_current_thread(branch) / set_current_thread(branch, thread_id) manage current thread pointer in state.json
- [x] Existing .session files migrated to .json on first read (read old format, write new format, remove old file)
- [x] Existing state.json fields preserved

## Worklog

- Created `src/kingdom/session.py` with AgentState dataclass and all CRUD helpers
- API: `get_agent_state`, `set_agent_state`, `update_agent_state` (read-modify-write convenience), `list_active_agents`, `get_current_thread`, `set_current_thread`
- Legacy migration: `get_agent_state` auto-detects `.session` files, reads resume_id, writes new `.json` format, removes old file. JSON takes precedence if both exist.
- `set_agent_state` omits None fields from JSON (keeps files clean for idle agents)
- `set_current_thread` does read-modify-write on state.json to preserve existing fields (e.g. `branch`)
- 24 tests in `tests/test_session.py` covering all acceptance criteria + edge cases
- Design note: used `set_agent_state(base, branch, name, state)` taking a full AgentState object rather than `**fields` — added `update_agent_state` as convenience wrapper for partial updates
