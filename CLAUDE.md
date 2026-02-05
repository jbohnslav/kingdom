# Kingdom Development Notes

## Python Environment

- Package manager: `uv`
- Activate venv: `source .venv/bin/activate`
- Run commands with venv active or use `uv run`

## Setup

After cloning, run `pre-commit install` to enable git hooks.

## .kd/ Directory

Everything in `.kd/` is tracked in git:
- `branches/` - active branch state (design.md, tickets/, learnings.md)
- `archive/` - completed branches
- `backlog/` - backlog tickets

Commit ticket work logs, closures, and branch archives. Only operational files are gitignored (`state.json`, `sessions/`, `logs/`).
