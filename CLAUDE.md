# Kingdom Development Notes

## Python Environment

- Package manager: `uv`
- Activate venv: `source .venv/bin/activate`
- Run commands with venv active or use `uv run`

## Setup

After cloning, run `pre-commit install` to enable git hooks.

## Style

Optimize for simple, readable, functional code.

Ask yourself
    - "Is this a real problem or imaginary?" -> reject over-design
    - "Is there a simpler way?" -> pick the smallest working solution

Rules
    - Follow the Zen of Python (readability, explicitness, simplicity).
    - Prefer pure functions, clear data flow, and immutability. Prefer helper functions over bloated classes with tons of methods.
    - Use classes when necessary and avoid overly deep inheritance trees.
    - No premature abstraction (worse than premature optimization); duplicate a little before you abstract.
    - Standard library > lightweight deps > heavy frameworks.
    - Fail loudly and explicitly; never swallow errors.
    - If it's hard to explain, it's a bad design.
    - Deliver a minimal, well-named module with docstrings, type hints, and a tiny usage example/test.
    - No functions beginning with underscores! Private functions are fake in python. Bad: `_send_to_agent()`: good: `send_to_agent()`.

## Tooling

When working with Python, invoke the relevant /astral:<skill> for uv, ty, and ruff to ensure best practices are followed.

## Workflow

Run `kd done` before creating or merging a PR. It verifies all tickets are closed.

## Skills

The kingdom skill lives at `skills/kingdom/SKILL.md` in this repo. `~/.claude/skills/kingdom` is a symlink to it — edit the repo copy.

## Agent Timeouts

Council queries can take several minutes. Set bash timeout to 5 minutes:

BASH_DEFAULT_TIMEOUT_MS=300000

## Testing

The full test suite must pass before closing a ticket. No exceptions — "pre-existing failure" is not an excuse to keep going. If tests you didn't write are failing, fix them or raise it with the King before proceeding.

After implementing a CLI command or changing its output, run it manually and check the output looks right. This catches things automated tests miss (formatting, unclear messaging, missing context). If it looks off, fix it — then wire the fix into an automated test if appropriate.

## Dogfooding

We use `kd` to develop `kd`. Every time you run a `kd` command, pay attention to the experience: Is the output helpful? Is anything confusing or missing? Would a different behavior be more natural? When you notice something off, immediately file a backlog ticket (`kd tk create --backlog "..."`). Don't wait to be asked — this is how we find real UX issues.
