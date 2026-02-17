# Plan: Restore Cursor Backend Code

## Context
Commit `4e7c196` and `d71d7fb` removed **all** cursor backend code when the intent was only to remove cursor from the council config/default agents. The cursor CLI (`agent`) should still be a supported backend — just not auto-created or included in the default council.

Two commits did the damage:
- `4e7c196` — removed cursor from agent.py (parsers, builders, extractors), config.py (DEFAULT_AGENTS, VALID_BACKENDS), poll.py (cursor branching), and most test removals
- `d71d7fb` — removed `merge_assistant_snapshots()` from poll.py, plus remaining cursor test helpers/classes
- `2a64eb9` — removed cursor from test_agent.py

## What stays removed (correct changes)
1. **config.py `DEFAULT_AGENTS`** — cursor should NOT be auto-created (users can add it manually)
2. **Council membership** — cursor should NOT be in the default council members
3. **`merge_assistant_snapshots()` in poll.py** — this was replaced with simple concatenation, which is correct (cursor fragments are NOT cumulative snapshots)
4. **Cursor branching in `poll_streams()` and `tail_stream_file()`** — the simplified concatenation path works for all backends

## What needs to be restored

### 1. `src/kingdom/agent.py`
- [ ] Docstring: restore "cursor" to backend list mention
- [ ] `BACKEND_DEFAULTS["cursor"]` entry
- [ ] `parse_cursor_response()` function
- [ ] `RESPONSE_PARSERS["cursor"]` entry
- [ ] `build_cursor_command()` function
- [ ] `COMMAND_BUILDERS["cursor"]` entry
- [ ] `extract_cursor_stream_text()` function
- [ ] `STREAM_TEXT_EXTRACTORS["cursor"]` entry
- [ ] `extract_cursor_stream_thinking()` function
- [ ] `STREAM_THINKING_EXTRACTORS["cursor"]` entry

### 2. `src/kingdom/config.py`
- [ ] `VALID_BACKENDS` — add "cursor" back
- [ ] Docstring comment on AgentDef.backend — restore "cursor"

### 3. `src/kingdom/tui/poll.py`
Nothing to restore here. The simplified concatenation path is correct for all backends including cursor.

### 4. `src/kingdom/tui/widgets.py`
Nothing cursor-specific was removed — changes were unrelated UX improvements.

### 5. `tests/test_agent.py`
- [ ] Restore `parse_cursor_response` import
- [ ] Restore `test_cursor_defaults()`
- [ ] Restore cursor in `test_all_backends_defined` assertion
- [ ] `test_resolve_all_defaults` — do NOT restore cursor here (it's not in DEFAULT_AGENTS anymore)
- [ ] Restore `test_cursor_without_session()`, `test_cursor_with_session()`
- [ ] Restore `test_cursor_with_model()`
- [ ] Restore `test_cursor_extra_flags()`
- [ ] Restore `test_cursor_skip_permissions_false()`, `test_cursor_skip_permissions_false_with_session()`
- [ ] Restore `TestParseCursorResponse` class
- [ ] Restore `test_cursor_streaming_replaces_output_format()`, `test_cursor_streaming_false_keeps_json()`
- [ ] Restore `TestParseCursorResponseNDJSON` class (full NDJSON test class — need to check what was in it)

### 6. `tests/test_config.py`
- [ ] `test_has_three_agents` → keep as `test_has_two_agents` (cursor NOT in DEFAULT_AGENTS)
- [ ] Keep cursor out of council defaults assertions
- [ ] Restore the `"local": {"backend": "cursor"}` custom agent test (proves cursor is a valid backend even if not a default)

### 7. `tests/test_tui_poll.py`
- [ ] Restore `cursor_assistant_event()` and `cursor_thinking_event()` test helpers
- [ ] Restore cursor-specific tests that test the *stream extraction* (these test `tail_stream_file` with cursor backend which still works via the extractors)
- [ ] Restore `TestRealCursorShortResponse`, `TestRealCursorEmptyResponse`, `TestRealCursorLongResponseWithToolCalls` classes
- [ ] Restore `TestCursorSnapshotEdgeCases` — but update to use simple concatenation (no `merge_assistant_snapshots`)
- [ ] Restore cursor thinking tests
- [ ] Restore cursor event ordering tests
- [ ] Do NOT restore `TestMergeAssistantSnapshots` or `TestCursorCrossBatchSnapshot` (merge function is gone, concat is correct)

## Approach
For each file, cherry-pick the removed code from before the removal commits. The pre-removal state can be found at `4e7c196^` (parent of the first removal commit).

Order of operations:
1. Restore agent.py backend code
2. Restore config.py VALID_BACKENDS
3. Restore test_agent.py tests
4. Restore test_config.py custom agent test
5. Restore test_tui_poll.py cursor tests (adapted for no merge_assistant_snapshots)
6. Run full test suite
