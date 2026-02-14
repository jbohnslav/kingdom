---
id: fc3f
status: closed
deps: [d52d]
links: []
created: 2026-02-14T14:12:21Z
type: task
priority: 2
---
# Add kd config show command

Add `kd config show` to print the effective config (defaults merged with user overrides).

## Details

- Add `config` command group to `cli.py`
- `kd config show` loads config via `load_config()` and prints the effective merged result as formatted JSON
- Shows what the system will actually use — resolves defaults + overrides so users can verify their config is correct
- If no config file exists, prints the defaults

## Acceptance Criteria

- [x] `kd config show` prints effective config as JSON
- [x] Output includes all sections: agents, prompts, council, peasant
- [x] Defaults are shown when no config file exists
- [x] User overrides are merged with defaults in the output
- [x] Command runs without error and output is valid JSON

## Worklog

- Added config_app Typer group with `kd config show` command
- Uses dataclasses.asdict() to serialize KingdomConfig to JSON
- Manually tested output: shows all sections, valid JSON
- Added 2 tests: defaults and user overrides
