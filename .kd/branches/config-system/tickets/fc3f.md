---
id: fc3f
status: open
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

- [ ] `kd config show` prints effective config as JSON
- [ ] Output includes all sections: agents, prompts, council, peasant
- [ ] Defaults are shown when no config file exists
- [ ] User overrides are merged with defaults in the output
- [ ] Command runs without error and output is valid JSON
