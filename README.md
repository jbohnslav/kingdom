# Kingdom

Kingdom (`kd`) is a markdown file-based CLI for software development: design with a multi-agent council, track work as markdown tickets, and run background RALPH loops with worker peasants.

The kingdom metaphor is intentional: you are the King, debate your design documents with a council of frontier coding agent CLIs you already use (Claude Code and Codex), break the design into modular markdown tickets, and then peasants execute those tickets in parallel worktrees.

Gastown minus the polecats.

## Why

- **Multi-agent council** — get perspectives from multiple frontier coding models, not just one opinion. Different models catch different things.
- **Ticket-based execution** — breaking work into scoped tickets fights context rot, lets you use cheaper models for already-designed work, or run tickets in parallel.
- **Multi-agent reviews** — reviews across models consistently catch bugs that single-agent reviews miss.
- **Plain markdown files** — tickets, designs, and council threads are all markdown. Your coding agents are already good at finding, reading, and updating markdown.
- **CLI + TUI** — the TUI is for humans; agent CLIs use `kd` directly to ask the council or other agents for opinions.
- **Worklog audit trail** — peasant worklogs capture decisions, bugs encountered, and test results in the ticket markdown, committed to git. You can always see *why* something was done, not just the diff.

## Install

```bash
uv tool install kingdom-cli  # add --python 3.11 if Python 3.11+ is not installed yet
```

Codex users can install the Kingdom skill and lifecycle hooks as one local plugin:

```bash
kd plugin install codex
```

Start a new Codex task after installation, then use `/hooks` to review and trust
the Kingdom hooks. Later `kd update` runs refresh an existing plugin along with
the CLI and skill files; they do not install the Codex plugin unless you opted in.

### Compaction checkpoints

Where a host exposes lifecycle hooks, Kingdom asks the exact bound session to
update its ticket before compaction or session handoff with decisions, completed
work, verification, blockers, and next steps. If automatic compaction cannot give
the model another turn first, the request is repeated immediately after compaction
and on compact-resume. Kingdom does not read unstable transcript formats or invent
handoff facts.

For hosts or modes without a usable pre-compaction hook, run `kd tk current`, edit
that ticket's Markdown directly, and record the same five fields before compacting
or handing off.

Cursor hook support is intentionally limited to behavior its public schema can
guarantee. See [Cursor hook capability](docs/cursor-hooks.md) for the supported
events and remaining attribution gaps.

## Workflow Scales

`kd` scales down gracefully. You pick the parts of the workflow that fit the size of the work.

### Full workflow (new features)

Design with the council, break into tickets, dispatch peasants, review, and merge.

```bash
kd start                   # initialize branch session
kd council chat --new      # discuss design with the council TUI
kd design approve          # lock in the design
# create tickets from the design (via the kingdom skill or manually)
kd peasant start <id>      # dispatch parallel workers
kd peasant review <id>     # review completed work
kd peasant accept <id>     # accept and close, or reject with feedback
kd done                    # archive and clean up
```

### Medium workflow (refactors, smaller features)

Pull tickets into a branch, work them directly or with peasants. No design phase needed.

```bash
kd start
kd tk pull <id> <id>       # pull backlog tickets onto this branch
kd tk start <id>           # work tickets one at a time
# if selected work is no longer for now:
kd tk defer <id> --reason "Waiting for upstream"
kd tk close <id>
kd done
```

### Lightweight workflow (bug fixes)

Work a single ticket, close it, make a PR. Or batch several bug-fix tickets on one branch.

```bash
kd start
kd tk create "fix: login redirect loop"
kd tk start <id>
# ... fix the bug ...
kd tk close <id>
kd done
```

Design docs, council sessions, and peasant workers are all optional. A branch with one ticket and no design doc is a perfectly valid `kd` workflow.

### Deprecated ticket command migrations

`kd tk defer <id>... --reason "..."` is the supported way to return selected
branch work to backlog. It records the source, previous status and assignee,
reason, time, and calling context in ticket lifecycle history, then resets the
ticket to open/unassigned and clears active bindings. Pull it again when the work
is timely.

`kd tk move` is deprecated and will be removed in v1.0.0. Replace backlog→work
movement with `kd tk pull`, work→backlog movement with `kd tk defer --reason`,
and branch→branch movement with defer, switch/check out the target branch, then
pull. The internal file-move primitive remains an implementation detail used by
pull, defer, archive/restore, and peasant workflows.

`kd tk add-note` is a hidden compatibility alias that will be removed in v0.8.0.
Use `kd tk log` instead; it preserves multiline input while adding the canonical
Worklog timestamp and author attribution.

### Ticket closure outcomes

`kd tk close <id>` records `resolution: completed` by default. The other terminal
resolutions are `wont-do`, `duplicate`, `superseded`, and `invalid`; each requires
a non-empty `--reason`. `--duplicate-of <id>` remains a shortcut that selects the
`duplicate` resolution and records the target; `--superseded-by <id>` does the
same for `superseded`. The active reason is stored as `close_reason`, and every
close or reopen is appended to the ticket's `## Lifecycle` section. Reopening
clears the active closure fields without erasing that history. Use
`kd tk list --resolution <value>` to filter terminal outcomes. When Kingdom can
identify the calling execution context, its stable ID is recorded as
`closed_context`; this is context attribution, not a separate human identity.
`kd done` validates terminal evidence before completing the branch and reports
the same per-resolution counts and non-completed outcomes in human or `--json`
output. Resolution-less legacy closures count as `duplicate`/`superseded` when
their matching reference field exists, and as `completed` otherwise.

## Getting Started

```bash
kd start                   # start a session on the current branch
```

Configure council agent CLIs in `.kd/config.json` (check effective config with `kd config show`).

## Chat Modes

The council chat TUI (`kd council chat`) supports four modes, configured via `council.chat.mode`:

| Mode | First turn | Auto-turns | Default |
|------|-----------|------------|---------|
| `natural` | parallel broadcast | shuffled round-robin | yes |
| `round_robin` | sequential fixed-order | sequential fixed-order | |
| `manual` | only @mentioned | only @mentioned | |
| `broadcast` | parallel to all | parallel to all | |

LLM-to-LLM @mentions in responses automatically bump the mentioned member to the front of the auto-turn queue.

## How It Works

All state lives in `.kd/` as plain Markdown and JSON files, tracked in git alongside your code:

```
.kd/
├── branches/                    # Active branch work
│   └── feature-oauth-refresh/
│       ├── design.md            # Design document
│       ├── breakdown.md         # Ticket breakdown
│       ├── tickets/             # Branch-specific tickets
│       │   ├── a1b2.md
│       │   └── c3d4.md
│       └── threads/             # Council discussion threads
├── backlog/                     # Unassigned tickets
│   └── tickets/
├── archive/                     # Completed branches
└── worktrees/                   # Git worktrees (gitignored)
```

No database. No server. Just files on disk.

## Commands

| Group | Description |
|-------|-------------|
| `kd start` / `kd done` / `kd status` | Branch lifecycle — initialize, finish, and inspect sessions |
| `kd design` | Manage design documents (`show`, `approve`) |
| `kd council` | Multi-model council — `ask`, `chat`, `review`, `show`, `list`, `watch`, `reset`, `retry` |
| `kd ticket` (alias `kd tk`) | Ticket management — `create`, `list`, `show`, `start`, `close`, `deps`, and more |
| `kd peasant` | Worker agents — `start`, `stop`, `review`, `accept`, `reject`, `msg`, `read`, `watch` |
| `kd config` | View and manage configuration |
| `kd plugin` | Install and inspect host integrations for Claude Code and Codex |
| `kd doctor` | Check config and agent CLIs |

Run `kd <command> --help` for full flags and options.

## Development

Inside a Kingdom checkout, always use `uv run kd` for dogfooding. Bare `kd` may
resolve to a separately installed release instead of the working tree.

```bash
uv sync
uv run pytest tests/
uv run ruff check .
uv run kd status
```

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
