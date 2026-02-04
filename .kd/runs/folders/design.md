# Design: Folder Restructuring & `kd init`

## Goal
Add a `kd init` command that creates the base `.kd/` structure separately from `kd start <feature>`, aligning CLI commands with the directory structure in `docs/cli-skill-architecture.md`.

## Context
Currently, `kd start <feature>` creates both the base `.kd/` structure AND the run-specific structure in one step. The architecture doc envisions a cleaner separation:
- `kd init` → bootstrap `.kd/` for the repo
- `kd start <feature>` → create a specific run/feature

Current `ensure_run_layout()` in `state.py` mixes both concerns. Additionally, some directories from the architecture doc are missing:
- `.kd/worktrees/` (referenced in gitignore but not created)
- `.kd/runs/<feature>/tickets/` (not created)
- `.kd/runs/<feature>/learnings.md` (not created)

## Requirements
1. **`kd init`** creates only base structure:
   - `.kd/`
   - `.kd/.gitignore` (with sane defaults)
   - `.kd/config.json` (empty skeleton)
   - `.kd/worktrees/`
   - `.kd/runs/`

2. **`kd start <feature>`** creates run structure (requires `kd init` first, or auto-inits):
   - `.kd/runs/<feature>/design.md`
   - `.kd/runs/<feature>/breakdown.md`
   - `.kd/runs/<feature>/learnings.md` (new)
   - `.kd/runs/<feature>/state.json`
   - `.kd/runs/<feature>/logs/council/`
   - `.kd/runs/<feature>/sessions/`
   - `.kd/runs/<feature>/tickets/` (new)

3. **Error handling for `kd init`**:
   - If `.kd/` exists: idempotent — create missing pieces, skip existing
   - If not a git repo: error, `--no-git` to override

4. **Error handling for `kd start`**:
   - If `.kd/` doesn't exist: auto-run init (or error with guidance)

## Non-Goals
- Changing the overall architecture or workflow
- Modifying `kd council`, `kd design`, `kd breakdown` commands
- Auto-migration of existing `.kd/` directories

## Decisions
- **Separation of concerns**: `kd init` for repo setup, `kd start` for feature runs. Rationale: cleaner mental model, matches architecture doc.
- **Idempotent init**: `kd init` creates missing pieces, skips existing. No `--force` needed. Rationale: simpler UX, no destructive operations anyway.
- **Auto-init on `kd start`**: If `.kd/` doesn't exist, `kd start` should auto-create it (with a message). Rationale: reduces friction for new users while keeping commands conceptually separate.
- **Default git validation**: `kd init` checks for git repo by default. Rationale: Kingdom workflow assumes git (worktrees, branches).
- **Auto-create `.gitignore`**: Always create with defaults, `--no-gitignore` to skip. Rationale: safe defaults prevent accidental commits.

## Implementation Plan

### 1. Refactor `state.py`
Split `ensure_run_layout()` into:
- `ensure_base_layout(base: Path) -> dict[str, Path]` — creates `.kd/` base
- `ensure_run_layout(base: Path, feature: str) -> dict[str, Path]` — creates run structure (calls base if needed)

Add missing paths:
- `worktrees_root(base: Path) -> Path`
- `tickets_root(base: Path, feature: str) -> Path`
- Create `learnings.md` in run layout

### 2. Add `kd init` command in `cli.py`
```python
@app.command(help="Initialize .kd/ directory structure.")
def init(
    no_git: bool = typer.Option(False, "--no-git", help="Skip git repo check"),
    no_gitignore: bool = typer.Option(False, "--no-gitignore", help="Skip .gitignore creation"),
) -> None:
    ...
```
Idempotent by default — creates missing pieces, skips existing.

### 3. Update `kd start` to auto-init
Check if `.kd/` exists, if not call init logic internally.

### 4. Update `.kd/.gitignore` content
Match architecture doc:
```
*.json
*.jsonl
runs/**/logs/
worktrees/
```

## Open Questions
- Should `kd init` also set up `.tickets/` (external ticket system)? Currently managed by `tk` tool.
- Council response: Codex recommends keeping init minimal. Agree - `.tickets/` is separate.
