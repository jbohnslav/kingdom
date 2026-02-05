---
id: kin-a8d9
status: closed
deps: []
links: []
created: 2026-02-05T03:12:07Z
type: task
priority: 1
---
# Add single-agent invocation to Council

Add ability to invoke a single council member instead of all 3.

Options:
- Add query_single(member_name: str, prompt: str) to Council class, or
- Add --agent <name> flag to kd council ask command

Reuse existing session management and logging.

Acceptance criteria:
- [x] Can invoke just Claude (or another specific member) without running all 3
- [x] Session continuity works the same as full council queries
- [x] Responses logged to the same bundle structure

## Work Log

### Implementation (2026-02-04)

**Approach:** Implemented both options from the spec:
1. Added `query_single(member_name, prompt)` method to `Council` class
2. Added `--agent/-a` flag to `kd council ask` command

**Key decisions:**
- `query_single()` raises `ValueError` for unknown member names (clear error handling)
- Exception handling in `query_single()` returns an `AgentResponse` with error field populated (matches `query()` behavior)
- Helper function `_query_single_with_progress()` handles the spinner UI for single-member queries

**Files changed:**
- `src/kingdom/council/council.py` - Added `query_single()` method
- `src/kingdom/cli.py` - Added `--agent` flag and `_query_single_with_progress()` helper
- `tests/test_council.py` - Added 6 tests for Council class and `query_single()`

**Commit:** 94146a9
