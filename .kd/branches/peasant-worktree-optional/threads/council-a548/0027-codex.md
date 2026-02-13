---
from: codex
to: king
timestamp: 2026-02-13T14:00:55Z
---

I’ll inspect the exact unstaged `cli.py` changes around environment handling (`launch_work_background` and council worker spawn), then evaluate whether stripping `CLAUDECODE` is sufficient and safe, plus potential edge cases.
I found the exact `CLAUDECODE` stripping sites. Next I’ll inspect surrounding process-spawn paths (including foreground `kd work`) for edge cases and then give a recommendation on whether to broaden or narrow env scrubbing.
I’m running the relevant test suites now to ensure this env handling doesn’t create regressions and to confirm current behavior around background worker launch paths.
**Findings**

1. **High**: Current fix is correct but **partial**.
`CLAUDECODE` is stripped only when spawning background wrappers:
- `src/kingdom/cli.py:423` (council worker `Popen`)
- `src/kingdom/cli.py:1048` (`launch_work_background`)

But backend CLIs are also run in-process in other paths and still inherit env:
- council `--sync` / `--json` end up in `CouncilMember.query` -> `subprocess.run(...)` without `env` at `src/kingdom/council/base.py:69`
- foreground `kd work` ends up in harness backend call -> `subprocess.run(...)` without `env` at `src/kingdom/harness.py:324`

So nested-Claude refusal can still happen in those modes.

2. **Medium**: Env scrubbing is duplicated and easy to drift.
Two ad-hoc comprehensions in `cli.py` (`src/kingdom/cli.py:423`, `src/kingdom/cli.py:1048`) should be centralized.

3. **Low**: Key match is exact-case only (`k != "CLAUDECODE"`).
On platforms with case-insensitive env semantics, defensive normalization is safer.

**Is it the right fix?**
- Yes for async/background launch paths.
- No as a complete solution across all execution modes.

**Other env vars to strip?**
- `CLAUDECODE` is the only one with clear evidence tied to nested-session refusal.
- I would **not** broadly strip `CODEX_*` / `OPENAI_*` / auth vars.
- Optional defensive candidate: `CLAUDE_CODE_ENTRYPOINT` (only if you confirm it also triggers nested checks in your Claude CLI version).

**Better approach**
1. Add one helper like `build_child_env()` and use it everywhere agent CLIs are executed.
2. Apply env sanitization at the **actual backend execution points** (`CouncilMember.query`, harness backend call), not only at wrapper `Popen`.
3. Add tests that assert `env` passed to subprocess for:
- council async launch
- council sync query
- work/harness backend execution

This gives uniform behavior for `kd council ask` (all modes) and `kd work` (foreground/background).
