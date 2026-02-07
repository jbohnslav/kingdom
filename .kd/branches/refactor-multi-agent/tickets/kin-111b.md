---
id: kin-111b
status: open
deps: [kin-56a5, kin-304a, kin-2d8e]
links: []
created: 2026-02-07T22:34:06Z
type: task
priority: 2
---
# Council refactor

Rewire kd council ask to use threads + agent configs. Merge ask/followup/critique into unified ask with --to flag. ask defaults to continue current thread if one exists, or start new thread if not. --thread new forces a new thread. Add kd council show [thread-id] and kd council list. Remove old followup and critique commands. Store council resume tokens in per-agent session files. Keep parallel execution via ThreadPoolExecutor. Existing council run bundles in logs/council/run-* remain readable but new queries go to threads.

## Acceptance
- [ ] kd council ask "prompt" creates thread on first use, continues on subsequent
- [ ] kd council ask --to codex "prompt" sends to one member only
- [ ] kd council ask --thread new "prompt" starts a fresh thread
- [ ] All messages written to thread directory as sequential .md files
- [ ] Resume tokens stored in sessions/<agent>.json, used on follow-up queries
- [ ] kd council show displays thread history with Rich panels
- [ ] kd council show falls back to logs/council/run-* for pre-migration runs
- [ ] kd council list shows all council threads
- [ ] Old followup and critique commands removed
