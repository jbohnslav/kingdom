# Kingdom Tech Stack

Technical decisions for the `kd` CLI implementation.

## Philosophy

**CLI-first over libraries.** Agents use CLIs anyway—Claude Code runs `git commit`, `tmux send-keys`, etc. Our orchestration code speaking the same language means less impedance mismatch, better debuggability, and fewer failure modes.

## Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "typer",      # CLI framework
        "rich",       # Pretty output
]

[project.scripts]
kd = "kingdom.cli:main"
```

That's it. Everything else is `subprocess.run()`:

- `tmux -L kd-<project> new-session ...`
- `git worktree add ...`
- `tk ready`
- `claude ...`

### Why CLI over libraries

| Concern | CLI approach | Library approach |
|---------|--------------|------------------|
| Stability | `tmux` and `git` CLIs are extremely stable | `libtmux`/`GitPython` break on upgrades |
| Debugging | Reproduce issues by running the same command | Debug Python binding internals |
| Failure modes | Check return codes, capture stderr | Binding-specific exceptions |
| Dependencies | Just Python stdlib + click | Keep bindings in sync with system tools |

### Subprocess patterns

```python
# Structured output when available
result = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True, text=True
)

# tmux list parsing
result = subprocess.run(
    ["tmux", "-L", "kd-kingdom", "list-windows", "-F", "#{window_name}"],
    capture_output=True, text=True
)
windows = result.stdout.strip().split("\n")
```

**Safety:** Always use list form of `subprocess.run()`, not `shell=True`, to avoid injection.

---

## Tmux Namespacing

Multiple features and projects can run concurrently without collisions.

### Naming scheme

| Component | Format | Example |
|-----------|--------|---------|
| **Server** | `kd-<project>` | `kd-kingdom`, `kd-otherapp` |
| **Session** | `<feature>` or `<feature>-<runId>` | `oauth-refresh`, `oauth-refresh-7f3a` |
| **Windows** | Fixed names | `hand`, `council`, `peasant-1`, `peasant-2` |

### Why this works

- **No collisions across repos** — server name scoped to project
- **No collisions across features** — session name scoped to feature
- **Easy to attach** — `tmux -L kd-kingdom attach -t oauth-refresh`
- **Easy to discover** — list sessions in a server

### Project derivation

Project name derived from repo folder (or explicit config):

```
/Users/jrb/code/kingdom   → kd-kingdom
/Users/jrb/code/otherapp  → kd-otherapp
```

### Session naming

For single runs per feature:

```
session: oauth-refresh
```

For multiple concurrent runs of the same feature:

```
session: oauth-refresh-20260125-1430
session: oauth-refresh-7f3a
```

### Architecture example

```
tmux server: kd-kingdom
├── session: oauth-refresh
│   ├── window: hand
│   ├── window: council
│   │   ├── pane: claude
│   │   ├── pane: gpt
│   │   ├── pane: gemini
│   │   └── pane: synthesis
│   ├── window: peasant-1
│   ├── window: peasant-2
│   └── window: peasant-3
│
└── session: api-refactor
    ├── window: hand
    ├── window: peasant-1
    └── window: peasant-2

tmux server: kd-otherapp
└── session: user-auth
    ├── window: hand
    └── window: peasant-1
```

---

## State Directory Structure

State paths include project and feature to match tmux namespacing.

```
.kd/
├── config.json                 # Global config (model settings, etc.)
├── current                     # Pointer to active run (e.g., "oauth-refresh")
├── runs/
│   ├── oauth-refresh/
│   │   ├── state.json          # Phase, Peasant count, tmux session info
│   │   ├── design.md           # Design document
│   │   ├── breakdown.md        # Ticket breakdown (deps + acceptance)
│   │   └── logs/
│   │       ├── hand.jsonl
│   │       ├── peasant-1.jsonl
│   │       └── peasant-2.jsonl
│   │
│   └── api-refactor-7f3a/      # Run with ID suffix
│       ├── state.json
│       ├── design.md
│       └── logs/
│
└── worktrees/
    ├── oauth-refresh/
    │   ├── peasant-1/          # Git worktree for Peasant 1
    │   ├── peasant-2/
    │   └── peasant-3/
    │
    └── api-refactor/
        ├── peasant-1/
        └── peasant-2/
```

Worktrees are scoped to feature, mirroring the tmux session structure. This allows multiple features to run concurrently with isolated working directories.

---

## CLI Scoping Behavior

### Default behavior (no flags)

| Command | Behavior |
|---------|----------|
| `kd start <feature>` | Creates session in current repo's server |
| `kd status` | Shows current feature (from `.kd/current`); lists active sessions if none |
| `kd attach` | Attaches to current feature's hand; prompts if ambiguous |
| `kd chat` | Attaches to current feature's hand |

### Explicit targeting

```bash
# Attach to specific session
kd attach --session oauth-refresh

# Attach to specific window
kd attach peasant-2 --session oauth-refresh

# Status for specific feature
kd status --session api-refactor
```

### Discovery

```bash
# List all active sessions for current project
kd list

# Raw tmux access
tmux -L kd-kingdom list-sessions
```

---

## External Tools

| Tool | Purpose | Interface |
|------|---------|-----------|
| `tmux` | Agent session management | CLI via subprocess |
| `git` | Version control, worktrees | CLI via subprocess |
| `tk` (ticket) | Ticket management | CLI via subprocess |
| `claude` | Claude Code CLI agent | CLI via subprocess |
| `codex` | Codex CLI agent | CLI via subprocess |
| `cursor` | Cursor CLI agent | CLI via subprocess |

### Why ticket (`tk`)

- Single bash script, no runtime dependencies
- Markdown files with YAML frontmatter—human readable, grep-able
- Built-in dependency graph (`tk dep`, `tk ready`, `tk blocked`)
- No daemon, no database, no sync issues

---

## Installation

With minimal deps, `uv tool install` is fast:

```bash
uv tool install kingdom
# or
pip install kingdom
```

Users get `kd` in their PATH.
