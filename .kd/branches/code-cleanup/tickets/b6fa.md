---
id: "b6fa"
status: closed
deps: []
links: []
created: 2026-03-03T05:39:47Z
type: bug
priority: 1
closed_at: 2026-03-03T05:45:07Z
---
# Fix issues from PR #32 Claude review

## From Claude PR review (#32)

### Bug 1: `drain()` ignores `label` parameter — dead code (harness.py:360)
`label` is passed as "stdout" and "stderr" but the function never uses it. Drop the parameter and the args.

### Bug 2: `worktree.py` git commands run without explicit `cwd` (worktree.py:64-84)
Both `git rev-parse --verify` and `git worktree add` inherit the calling process CWD. Should pass `cwd=base` to all git subprocess calls. `remove_worktree` has the same issue.

### Bug 3: Silent failure in `peasant_watch` swallows agent backend resolution errors (cli/peasant.py:765)
Bare `except Exception: pass` means `agent_backend` silently stays as `""`. Watch shows no streaming output without any warning. At minimum log or print a warning.

### Nit 1: Redundant exception types in `filter_agent_log_lines` (cli/peasant.py:558)
`json.JSONDecodeError` is a subclass of `ValueError`. Catching both is redundant. Use one or the other.

### Nit 2: `parsing.py` YAML list parser splits on all commas
Breaks for list items containing commas. Low-risk since ticket IDs are 4-char hex, but worth a comment noting the limitation.

### Nit 3: `collect_all_tickets` inline json import (ticket.py:224)
`import json` inside a for-loop body — move to top of function or module.

## Acceptance Criteria

- [ ] Remove unused `label` param from `drain()` in `run_streaming_subprocess`
- [ ] Add `cwd=base` to all git subprocess calls in `worktree.py`
- [ ] Replace bare `except Exception: pass` with a warning in `peasant_watch`
- [ ] Fix redundant exception types in `filter_agent_log_lines`
- [ ] Add comment about comma limitation in `parsing.py` list parser
- [ ] Move inline `import json` to module/function top in `ticket.py`
- [ ] All tests pass

## Acceptance Criteria

- [ ]
