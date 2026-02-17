---
from: claude
to: king
timestamp: 2026-02-17T13:08:13Z
---



Let me move `textual` from the dependency group to the main dependencies.Now let me find and remove the conditional import guard for textual.Now let me also check where `require_textual()` is called.Let me read the relevant sections of the CLI and the tui init to understand the full guard path.Now I have the full picture. Three changes needed:

1. Move `textual` from `[dependency-groups] chat` to `[project] dependencies`
2. Remove the `require_textual()` guard and its call site in `cli.py`
3. Update the test that expects the guard to work
4. Update the `tui/__init__.py` module docstring

Let me also update the architecture doc that mentions it's optional.Looks like I don't have write permissions. The King said I should — let me know if you'd like to grant edit access and I'll make these changes:

1. **`pyproject.toml`**: Add `textual>=7.5.0` to `[project] dependencies`, remove the `[dependency-groups] chat` group entirely
2. **`src/kingdom/tui/__init__.py`**: Remove `require_textual()` function, update module docstring
3. **`src/kingdom/cli.py`** (~line 1344-1350): Remove the `require_textual()` guard — just import directly
4. **`tests/test_tui.py`**: Remove `TestRequireTextual` class (the "missing textual" test is no longer meaningful)
5. **`docs/architecture.md`**: Update the line that says TUI is an optional dependency group
