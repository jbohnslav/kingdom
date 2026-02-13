---
from: peasant-kin-760e
to: king
timestamp: 2026-02-11T02:40:03Z
---

## What I did this iteration

1. **Identified the duplication**: Found identical `split('---', 2)` + `split(':', 1)` frontmatter parsing in `ticket.py:170-202`, `agent.py:57-78`, and `thread.py:282-302`. All three also shared `parse_yaml_value` (defined in `ticket.py`, imported by the other two).

2. **Created `src/kingdom/parsing.py`**: A new shared module containing:
   - `parse_yaml_value()` — moved from `ticket.py`
   - `serialize_yaml_value()` — moved from `ticket.py`
   - `parse_frontmatter(content) -> (dict, body)` — the new unified parser
   - `FrontmatterDict` type alias

3. **Replaced all three inline parsers**:
   - `ticket.py`: `parse_ticket()` now calls `parse_frontmatter(content)` instead of inlining the split logic (removed ~20 lines of duplicated code)
   - `agent.py`: `parse_agent_file()` now calls `parse_frontmatter(content)` (removed ~15 lines)
   - `thread.py`: `parse_message()` now calls `parse_frontmatter(content)` (removed ~17 lines)
   - Updated imports in all three files to use `kingdom.parsing`

4. **Added 42 tests** in `tests/test_parsing.py` covering edge cases: colons in values (URLs, timestamps), empty/null values, blank lines in frontmatter, triple-dashes in body content, quoted strings, lists, integers, missing delimiters, etc.

5. **Verified**: All 426 tests pass (384 existing + 42 new), no regressions. Pre-commit hooks pass.

## Acceptance criteria met
- Three duplicate parsers replaced with single `parse_frontmatter` utility
- Used stdlib (no PyYAML needed — the existing custom parser handles the simple YAML subset used by this project)
- Tests for edge cases added (42 tests)
- All existing tests continue to pass

STATUS: DONE
