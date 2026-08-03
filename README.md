# Kingdom

Kingdom (`kd`) is a ticket-first CLI for software development with multiple AI
agents. Work lives in plain Markdown tickets and epics, each agent session gets
its own execution context, and decisions and verification stay durable in the
ticket worklog.

Start with the small loop. Add the TUI, multi-model council, reviewed peasant
workers, or an epic-level lord only when the work benefits from them.

## Install

```bash
uv tool install kingdom-cli  # add --python 3.11 if Python 3.11+ is not installed yet
```

Then initialize the current Git branch:

```bash
kd start
```

Codex users can install the Kingdom skill and lifecycle hooks as one local
plugin:

```bash
kd plugin install codex
```

Start a new Codex task after installation, then use `/hooks` to review and trust
the Kingdom hooks. Later `kd update` runs refresh an existing plugin along with
the CLI and skill files; they do not install the Codex plugin unless you opted in.

See the dated [supported host integration matrix](docs/support-matrix.md) for
verified versions, evidence levels, and known Claude, Codex, and Cursor limits.

## Core ticket loop

The everyday workflow is create or find, select and start, keep the worklog
current, then close with evidence.

### 1. Create or find the work

Create one small ticket for genuinely new work:

```bash
kd tk create "Fix login redirect loop"
kd tk find <id>                 # print the canonical Markdown file path
```

If the request may already exist, inspect the current and recent work before
creating another ticket:

```bash
kd tk current
kd tk list
kd tk list --recently-closed --limit 10
kd tk show <id>
```

Tickets are living Markdown documents. Edit the file directly for requirements,
acceptance criteria, relationships, and rich worklog entries.

### 2. Pull or start it

Capture unplanned work in the backlog, then select it when it becomes timely:

```bash
kd tk create --backlog "Improve retry diagnostics"
kd tk pull <id>
kd tk start <id>
```

`kd tk start` binds only the calling execution context. Other agent sessions can
start and own different tickets concurrently.

### 3. Log and close

Record durable findings while they are fresh, not only at the end:

```bash
# Plain-text-only notes without shell metacharacters may be inline.
kd tk log <id> "Root cause confirmed; regression test now passes"
kd tk close <id>
```

Send command-rich or multiline notes through stdin with a quoted delimiter so
the shell cannot expand backticks, `$()`, variables, or quotes:

```bash
kd tk log <id> <<'WORKLOG'
Verified `uv run pytest`; literal $HOME and $(pwd) were not expanded.
Record the second line here.
WORKLOG
```

Alternatively, edit the ticket's `## Worklog` as direct Markdown. Before
closing, check off acceptance criteria and record changed files, decisions,
verification commands, results, and remaining concerns.

### 4. Organize related work with epics

An epic is a parent ticket for a concrete outcome. Its children remain normal,
independently executable tickets:

```bash
kd tk create --type epic "Ship account recovery"
kd tk create --parent <epic-id> "Add recovery-token storage"
kd tk create --parent <epic-id> "Implement recovery endpoint"
kd tk list --parent <epic-id>
```

## Concurrent agent contexts

Each terminal, Codex task, Claude session, or native subagent can have a distinct
execution context. Starting a ticket in one context does not replace another
context's current ticket.

```bash
# Agent session A
kd tk start api1
kd tk current                  # api1

# Agent session B, at the same time
kd tk start ui2
kd tk current                  # ui2

kd status                      # branch-wide tickets and all agent contexts
```

`kd status` shows each context's host, role, ticket, epic, activity, and parent
context when available. The owning session remains responsible for integrating
delegated results into the working tree and durable ticket—even when hooks record
an automatic child handoff.

### Compaction checkpoints

Where a host exposes lifecycle hooks, Kingdom asks the exact bound context to
update its ticket before compaction or handoff with decisions, completed work,
verification, blockers, and next steps. If automatic compaction cannot give the
model another turn first, the request is repeated immediately after compaction
and on compact-resume.

For hosts or modes without a usable pre-compaction hook, run `kd tk current`, edit
that ticket's Markdown directly, and record the same five fields before
compacting or handing off. See [Cursor hook capability](docs/cursor-hooks.md) for
the supported Cursor events and remaining attribution gaps.

## Execution choices

### Direct work

Use direct work for small, sequential, integration-sensitive tickets:

```bash
kd tk start <id>
# implement, test, and update the Markdown worklog
kd tk log <id> "Verified with: pytest tests/test_login.py"
kd tk close <id>
```

### Bounded native subagent

Use the current host's native subagent feature for a bounded research, review, or
independent implementation slice. The owning session keeps ticket ownership,
reviews the child's output, integrates the useful changes, and writes the durable
conclusion into the ticket:

```bash
kd tk start <id>
# delegate one bounded slice with the host's native subagent tool
# owning session reviews and integrates the returned work
kd tk log <id> "Integrated subagent audit; findings and verification recorded"
```

## Power tools

These tools are optional. The core ticket loop works without any of them.

### Reviewed peasant

A peasant runs a well-scoped ticket unattended in an isolated worktree and uses
council review by default. The owning session still performs the final
integration review:

```bash
kd peasant start <id>
kd peasant watch <id>
kd peasant review <id>         # diff, worklog, and council feedback
kd peasant accept <id>         # or: kd peasant reject <id> "feedback"
```

### TUI and council

Use the council for genuine design ambiguity, product tradeoffs, or independent
review blind spots. The chat TUI is a human-friendly way to hold the same
multi-model discussion:

```bash
kd council ask "Which migration strategy best preserves rollback safety?"
kd council chat                 # create a new thread
```

Council output advises the ticket owner; it does not replace the implementation
worker or durable decision record.

### Lords

A lord supervises several ready child tickets under an epic, delegates them to
reviewed peasants, and checks cross-ticket integration:

```bash
kd lord start <epic-id> --watch
kd lord status
```

### Optional design documents

Design documents are optional planning artifacts, not a prerequisite for tickets
or backlog sprints. Use them when cross-cutting ambiguity merits a dedicated
artifact; existing repositories and commands remain supported:

```bash
kd design                       # initialize and print the design path
# edit the design document when the extra planning artifact is useful
kd design show
kd design approve
```

## Deprecated ticket command migrations

The checkout remains on the 0.6.x compatibility window until the final 1.0.0
version cut. The removal versions below are release boundaries, not claims that
the compatibility aliases have already disappeared from this pre-cut tree. See
the [1.0.0 release notes](docs/releases/1.0.0.md) for the final-cut gate.

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
Worklog timestamp and author attribution. Because the next planned release jumps
from 0.6.x to 1.0.0, the final cut must remove this alias as well as `kd tk move`.

## Ticket closure outcomes

`kd tk close <id>` records `resolution: completed` by default. The other terminal
resolutions are `wont-do`, `duplicate`, `superseded`, and `invalid`; each requires
a non-empty `--reason`. `--duplicate-of <id>` and `--superseded-by <id>` record
their target ticket. Closing appends lifecycle history; reopening clears active
closure fields without erasing that history.

Use `kd tk list --resolution <value>` to filter terminal outcomes. `kd done`
validates terminal evidence before completing a branch and reports the same
resolution breakdown. Resolution-less legacy closures remain readable and map
to their compatible inferred outcome.

## Upgrading existing repositories

`kd update` refreshes the CLI and configured host integrations. Existing `.kd`
repositories use a lazy, idempotent context migration that preserves ticket IDs
and Markdown. Back up `.kd`, verify with the read-only `kd doctor`, and use the
retained legacy context state if you need to roll back. See the complete
[upgrade and rollback guide](docs/upgrading.md).

## How it works

All state lives in `.kd/` as plain Markdown and JSON tracked with the code:

```text
.kd/
├── branches/
│   └── feature-oauth-refresh/
│       ├── tickets/             # active tickets and epics
│       ├── design.md            # optional planning artifact
│       ├── breakdown.md         # optional legacy planning artifact
│       └── threads/             # council discussions and reviews
├── backlog/tickets/             # work not selected yet
├── archive/                     # completed branches and tickets
└── worktrees/                   # peasant worktrees (gitignored)
```

No database. No server. Just files on disk.

## Commands

| Group | Description |
|-------|-------------|
| `kd ticket` / `kd tk` | Create, find, pull, start, log, relate, and close tickets and epics |
| `kd status` | Show branch ticket progress and concurrent agent contexts |
| `kd start` / `kd done` | Initialize/resume and validate/finish branch work |
| `kd council` | Power tool for multi-model questions, reviews, and the chat TUI |
| `kd peasant` | Power tool for reviewed unattended ticket workers |
| `kd lord` | Power tool for epic-level peasant orchestration |
| `kd design` | Optional design-document planning (hidden from root help) |
| `kd config` / `kd doctor` | Inspect configuration, repository state, and host integrations |
| `kd plugin` / `kd update` | Install and refresh host integrations |

Run `kd <command> --help` for exact flags.

## Development

Inside a Kingdom checkout, always use `uv run kd` for dogfooding. Bare `kd` may
resolve to a separately installed release instead of the working tree.

```bash
uv sync
uv run pytest tests/
uv run ruff check .
uv run ruff format --check .
uv run pre-commit run ruff --all-files
uv run pre-commit run ruff-format --all-files
uv run kd status
```

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
