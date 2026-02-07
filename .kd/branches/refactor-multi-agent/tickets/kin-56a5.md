---
id: kin-56a5
status: in_progress
deps: []
links: []
created: 2026-02-07T22:33:42Z
type: task
priority: 1
---
# Thread model

Core data model for threads. Create/read/write thread directories under .kd/branches/<branch>/threads/<thread-id>/. Thread metadata in thread.json (members, pattern, created_at). Sequential message files (0001-king.md, 0002-claude.md) with YAML frontmatter (from, to, timestamp, refs). Thread IDs are sanitized using the existing normalize_branch_name() function. Helpers: create_thread(), add_message(), list_messages(), list_threads(), next_message_number().

## Acceptance
- [ ] create_thread(branch, thread_id, members, pattern) creates directory + thread.json
- [ ] Thread IDs are normalized via normalize_branch_name() (same sanitization as branch directories)
- [ ] add_message(branch, thread_id, from_, to, body, refs) writes next sequential .md file
- [ ] list_messages(branch, thread_id) returns messages in order
- [ ] list_threads(branch) returns all thread IDs with metadata
- [ ] Messages use YAML frontmatter matching the design doc format
- [ ] Tests cover create, add, list, sequential numbering
