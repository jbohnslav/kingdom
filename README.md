# Kingdom

Kingdom (`kd`) is a ticket-first CLI for software development with multiple AI
agents. Work lives in plain Markdown tickets and epics, each agent session gets
its own execution context, and each ticket captures current understanding with
useful history and verification evidence.

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

Represent each unit of work once, keep its ticket accurate as understanding
evolves, and close with evidence. The commands below are examples, not a
checklist to repeat on every turn.

### 1. Create or find the work

Create one small ticket for genuinely new work:

```bash
kd tk create "Fix login redirect loop"
kd tk find <id>                 # print the canonical Markdown file path
```

Reuse the known ticket on follow-ups. When context is missing, choose the lookup
that answers your question: `kd tk current` for ownership, `kd tk list` to select
work, or `kd tk show <id>` for unread details. Search recently closed tickets only
when looking for completed work.

The ticket body is the working document. Edit purpose, scope, acceptance criteria,
plan, and findings directly; rewrite stale text rather than appending corrections.
Use lifecycle commands for status, ownership, and structured relationships.

### 2. Pull or start it

Capture unplanned work in the backlog, then select it when it becomes timely:

```bash
kd tk create --backlog "Improve retry diagnostics"
kd tk pull <id>
kd tk start <id>
```

`kd tk start` binds only the calling execution context. Other agent sessions can
start and own different tickets concurrently.

### 3. Keep the ticket current and close with evidence

Keep current findings in the body. Use the worklog for useful history and
verification evidence, either by editing it directly or appending a note:

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

Before closing, ensure the body reflects the result, acceptance criteria are
met, and verification evidence is recorded. Routine turns need no ticket update
when nothing durable changed.

### 4. Organize related work with epics

An epic is a parent ticket for a concrete outcome. Its children remain normal,
independently executable tickets:

```bash
kd tk create --type epic "Ship account recovery"
kd tk create --parent <epic-id> "Add recovery-token storage"
kd tk create --parent <epic-id> "Implement recovery endpoint"
kd tk list --parent <epic-id>
```

### 5. Check workspace readiness

Status is the end of the loop; there is no separate workspace-finalization step:

```bash
kd status                      # inspect tickets and active contexts
kd status --check              # exit nonzero unless every ticket is terminal and valid
```

`kd status --check` is read-only, so it is safe for local review, CI, and release
gates. Workspace readiness is derived from ticket state rather than stored as a
separate branch lifecycle transition.

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

## Resource cleanup

Cleanup stays with the command that owns each resource; there is no global
end-of-work cleanup command:

- `kd tk close` and `kd tk defer` clear active bindings for the affected ticket.
- `kd status --prune-stale` removes stale execution-context bindings.
- `kd peasant accept` integrates reviewed work and cleans its worker state;
  `kd peasant clean <id>` removes one retained worktree, and
  `kd peasant prune` removes stale peasant sessions and orphaned state.

## Execution choices

### Direct work

Use direct work for small, sequential, integration-sensitive tickets:

```bash
kd tk start <id>
# implement, test, and keep the ticket body accurate
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
# owning session reviews the result and consolidates findings in the ticket body
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
```

## Consolidated command replacements

Kingdom 1.0.0 consolidates four command routes. Existing repositories keep their
Markdown history; only the commands used for readiness, workspace selection,
ticket movement, and Worklog entries change. See the
[1.0.0 release notes](docs/releases/1.0.0.md) for the complete upgrade boundary.

`kd tk defer <id>... --reason "..."` is the supported way to return selected
branch work to backlog. It records the source, previous status and assignee,
reason, time, and calling context in ticket lifecycle history, then resets the
ticket to open/unassigned and clears active bindings. Pull it again when the work
is timely.

`kd done` was removed in v1.0.0. Use the read-only `kd status --check` readiness
gate after closing tickets and epics. There is no replacement finalization
transition and no `--force` bypass; readiness is derived from ticket state.

`kd switch <branch>` was removed in v1.0.0. Use `kd start <branch>` to initialize,
resume, or select a workspace through one idempotent entry point.

Use `kd tk move <id> --to-branch <branch>` to relocate a ticket from a branch,
backlog, or archive onto an existing branch board. This preserves the complete
ticket file,
including status and closure evidence, without checking out or selecting another
branch. A moved closed ticket stays closed; relocation does not reopen it.
Active native or peasant workers must finish or release ownership first.

Use `kd tk pull` to select backlog work and `kd tk defer --reason` to return work
to the backlog. Deferral intentionally resets status and assignment and refuses
closed tickets; use `move` when relocating work whose state must be preserved.

`kd tk add-note` was removed in v1.0.0. Use `kd tk log`; it preserves multiline
input while adding the canonical Worklog timestamp and author attribution. The
direct 0.6.x→1.0.0 upgrade crossed the alias's previously announced v0.8.0
removal boundary.

## Ticket closure outcomes

`kd tk close <id>` records `resolution: completed` by default. The other terminal
resolutions are `wont-do`, `duplicate`, `superseded`, and `invalid`; each requires
a non-empty `--reason`. `--duplicate-of <id>` and `--superseded-by <id>` record
their target ticket. Closing appends lifecycle history; reopening clears active
closure fields without erasing that history.

Use `kd tk list --resolution <value>` to filter terminal outcomes.
`kd status --check` validates terminal evidence and reports the same resolution
breakdown without changing workspace state. Closed tickets need an explicit
valid resolution; missing closure evidence fails readiness checks.

## Upgrading existing repositories

`kd update` refreshes the CLI and configured host integrations. Existing `.kd`
repositories use the current branch and execution-context formats. Old runtime
formats are no longer migrated or read. Back up `.kd` before upgrading and verify
with the read-only `kd doctor`. See the complete
[upgrade and rollback guide](docs/upgrading.md).

## How it works

All state lives in `.kd/` as plain Markdown and JSON. Tickets and discussions
are tracked with the code; runtime state is gitignored:

```text
.kd/
├── branches/
│   └── feature-oauth-refresh/
│       ├── tickets/             # active tickets and epics
│       ├── design.md            # optional planning artifact
│       └── threads/             # council discussions and reviews
├── backlog/tickets/             # work not selected yet
├── archive/                     # completed branches and tickets
├── runtime/contexts/            # execution-context bindings (gitignored)
└── worktrees/<branch>/<ticket>/ # peasant worktrees (gitignored)
```

No database. No server. Just files on disk.

## Commands

| Group | Description |
|-------|-------------|
| `kd ticket` / `kd tk` | Create, find, pull, start, log, relate, and close tickets and epics |
| `kd start [branch]` | Initialize, resume, or select a workspace |
| `kd status [--check]` | Show ticket/context state and optionally enforce workspace readiness |
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
uv run pytest --run-textual-integration
uv run ruff check .
uv run ruff format --check .
uv run pre-commit run ruff --all-files
uv run pre-commit run ruff-format --all-files
uv run kd status
```

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
