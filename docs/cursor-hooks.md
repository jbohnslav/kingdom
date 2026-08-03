# Cursor hook capability

Status verified: 2026-08-03. Cursor hook configuration schema: version 1.

Kingdom recommends a **limited Cursor adapter**, not parity with the Claude and
Codex integrations. Cursor now publishes stable identifiers and lifecycle hooks,
so Kingdom can isolate conversation state and observe subagent creation. Its public
schema still lacks two capabilities needed for complete ticket attribution.

## Official capability evidence

The current [Cursor Hooks reference](https://cursor.com/docs/hooks) documents:

- `conversation_id`, a stable ID across turns, and `workspace_roots` in the common
  input schema;
- local `sessionStart` and `sessionEnd` hooks, with `session_id` equal to
  `conversation_id`;
- `subagentStart`, including stable `subagent_id`, `subagent_type`, and
  `parent_conversation_id` fields;
- `preCompact`, an observational hook that can return a visible `user_message`;
- project hooks in `.cursor/hooks.json`, user hooks in `~/.cursor/hooks.json`, and
  command hooks that exchange JSON over standard input and output;
- project command hooks in cloud agents, including `subagentStart`,
  `subagentStop`, `preCompact`, and `stop`. Cloud agents do not run
  `sessionStart` or `sessionEnd`, and do not load user-level hooks.

Cursor announced the broader conversation, subagent, and compaction hook surface
in the [Cursor 3.11 changelog (2026-07-10)](https://cursor.com/changelog/side-chat).

## Prototype result

`kd hook run --host cursor` now accepts the published JSON shapes. Tests prove
that stable conversation identifiers resolve to isolated Kingdom execution
contexts and that `subagentStart` records a child context linked to the exact
parent ticket. Cursor responses use Cursor's own schemas:

| Event | Kingdom behavior |
| --- | --- |
| `sessionStart` | Supplies `KD_CONTEXT`, `KD_HOST`, and initial workflow context. |
| `beforeSubmitPrompt` | Starts isolated turn tracking and allows the prompt. |
| `preCompact` | Requests an exact-ticket checkpoint through `user_message`. |
| `subagentStart` | Records the stable child/parent relationship and allows creation. |
| `postToolUse` | Observes content-free worklog signals. |
| `stop` | Uses `followup_message` once when meaningful work was not logged. |
| `sessionEnd` | Records checkpoint state, but emits no message because responses are ignored. |

The `sessionStart` environment is useful to later hooks. Cursor's documentation
does not promise that those variables reach arbitrary shell tools run by the
agent, so Kingdom does not claim that every `kd tk start` invocation is
automatically conversation-bound.

## Known limits

- `subagentStart` can allow or deny creation, but its documented response cannot
  add context to an allowed child. Kingdom records inheritance but cannot promise
  the subagent was told to read the ticket.
- The documented `subagentStop` input omits `subagent_id`. Kingdom cannot safely
  correlate completion to a particular concurrently running child, so it does not
  close that child context or append an exact completion handoff.
- Cursor has no `postCompact` event. Kingdom can request a checkpoint immediately
  before compaction but cannot repeat it automatically after compaction.
- Cloud agents may begin read-only before repository hooks load. Their earliest
  turns therefore cannot be tracked by a project hook.

These are deliberate gaps. Kingdom must not infer identity from recency, prompt
text, transcript contents, or an arbitrary active ticket.

## Installation, security, and portability

Project hooks execute repository commands automatically in trusted workspaces;
review `.cursor/hooks.json` and its scripts like executable code. Cursor hooks are
fail-open by default, and Kingdom keeps that default so a broken tracking hook
cannot block agent work or exit. Organizations that use `failClosed` for security
policy should keep Kingdom's observational hooks separate from enforcement hooks.

Project-relative commands run from the repository root. User hooks run from
`~/.cursor/`. Enterprise hook locations differ across macOS, Linux/WSL, and
Windows, and cloud agents only receive project, team, or enterprise command hooks.
Kingdom's adapter reads JSON through standard input, writes JSON through standard
output, uses `workspace_roots` instead of platform-specific path inference, and
does not retain prompts, responses, task descriptions, summaries, email addresses,
or transcript paths.
