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
