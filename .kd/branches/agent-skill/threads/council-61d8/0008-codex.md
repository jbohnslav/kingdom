---
from: codex
to: king
timestamp: 2026-02-14T03:22:27Z
---

I’ll read the updated `.kd/branches/agent-skill/design.md` and quickly cross-check against current CLI/repo reality, then give a go/no-go with any remaining issues.
1. **High: Python version in skill is currently wrong vs package reality.**
Design says `Python 3.10+` in frontmatter/prereqs, but package requires `>=3.12`. Agents on 3.10/3.11 will fail install.
Refs: `.kd/branches/agent-skill/design.md:88`, `.kd/branches/agent-skill/design.md:94`, `pyproject.toml:6`

2. **Medium: prerequisite verification step is incorrect.**
`kd doctor` does not verify that `kd` is installed; it checks agent CLIs. For skill preflight, use `command -v kd` (or `kd --help`) plus `kd doctor` separately for backend readiness.
Refs: `.kd/branches/agent-skill/design.md:94`, `src/kingdom/cli.py:1934`

3. **Low: “Complete command inventory” is not actually complete.**
It omits multiple existing commands (notably several `peasant` subcommands and some `ticket` subcommands like `reopen`). Either rename section to “core command inventory” or include all commands.
Refs: `.kd/branches/agent-skill/design.md:102`, `src/kingdom/cli.py:1221`, `src/kingdom/cli.py:1308`, `src/kingdom/cli.py:1350`, `src/kingdom/cli.py:1390`, `src/kingdom/cli.py:1408`, `src/kingdom/cli.py:1481`, `src/kingdom/cli.py:1520`, `src/kingdom/cli.py:1555`, `src/kingdom/cli.py:2350`

4. **Low: deleting root `SKILL.md` is correct, but add explicit migration guard.**
Good decision; just ensure any existing docs/workflows that point to root `SKILL.md` are updated in the same PR to avoid dangling references.
Refs: `.kd/branches/agent-skill/design.md:50`, `.kd/branches/agent-skill/design.md:134`

Open question recommendation (`kd install-skill`):
- Prefer **not** coupling skill install to PyPI initially. Keep `skills/kingdom/` as source-of-truth in repo.
- If you add `kd install-skill` later, treat it as a convenience command that copies packaged data files from the installed wheel, not as a second divergent skill source.

**Verdict:** Almost ready. Fix items 1 and 2 before implementation; item 3 is wording/scope cleanup. After that, go implement.
