# Kingdom Development Notes

## Python Environment

- Package manager: `uv`
- Activate venv: `source .venv/bin/activate`
- Run commands with venv active or use `uv run`

## Setup

After cloning, run `pre-commit install` to enable git hooks.

## Agent Timeouts

Council queries can take several minutes. Set bash timeout to 5 minutes:

BASH_DEFAULT_TIMEOUT_MS=300000

## Dogfooding

We use `kd` to develop `kd`. When you encounter usability issues, unintuitive behavior, or product feedback while using `kd` commands, capture it — either as a note in the current ticket's worklog or as a new backlog ticket if it's actionable.
