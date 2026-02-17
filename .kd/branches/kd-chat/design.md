# Design: kd-chat

## Goal

Build a dedicated `kd chat` TUI as a sidecar for rich, streaming, multi-agent group chat. Runs in a separate terminal pane alongside Claude Code. Feel like a Slack thread with three engineers: you send a message, see responses stream in with color-coded panels, and the councillors discuss amongst themselves with bounded auto-turns.

## Context

The council today works but the interaction model is CLI-first: send a message, wait behind a spinner, get walls of text. The council-improvements branch (merged as #15) added streaming, retry, richer status, and UX polish to the CLI path. The thread/messaging system and stream-json infrastructure built there are the key enablers — the TUI becomes a pure view+input layer over thread files, not a stateful monolith.

### Streaming infrastructure (from council-improvements)

Both Claude Code and Cursor support `--output-format stream-json` which emits NDJSON. Council queries already use streaming mode. `.stream-{member}.jsonl` files capture live output line-by-line. Each line is a complete JSON object — text is extractable via `text_delta` events for Claude, backend-specific formats for others.

**Per-backend streaming behavior:**

| Backend | CLI flags | Stream file usefulness |
|---------|-----------|----------------------|
| **Claude Code** | `--output-format stream-json --verbose --include-partial-messages` | **Excellent.** Token-level NDJSON, each line parseable. |
| **Codex** | `--json` (unchanged) | **Good.** JSONL events as before. |
| **Cursor** | `--output-format stream-json` | **Good to excellent.** NDJSON events per turn; token-level TBD. |

### What already exists

- Thread files as source of truth (`.kd/branches/.../threads/<id>/`)
- `.stream-{member}.jsonl` files with live NDJSON output during execution
- NDJSON parsers extracting `text_delta` text for readable display
- `watch_thread()` tailing stream files alongside polling for finalized messages
- Council member query infrastructure with streaming support
- `CouncilMember.build_command()` with prompt merge: safety preamble + phase prompt + agent prompt + user prompt
- Session state per-branch+member in `.kd/branches/<branch>/sessions/<agent>.json`
- Thread messages as sequential `NNNN-{sender}.md` files with YAML frontmatter
- Concurrency-safe message writing via exclusive-create mode

### What does NOT exist yet

- `council.auto_rounds`, `council.mode`, `council.preamble` config keys — not in schema yet, will fail validation if set
- `kd chat` CLI command
- ~~Textual dependency~~ (added: `[dependency-groups] chat` in pyproject.toml)
- Thread-scoped session management (current sessions are per-branch+member, not per-thread)
- Round/turn metadata for group chat (current status model only tracks responses to latest king message)

## Requirements

### Phase 1: `kd chat` TUI

#### Core behavior
- Dedicated Textual app, runs in a separate terminal pane
- Opens existing thread or creates new one:
  - `kd chat` — resumes current thread (from branch state.json `current_thread`)
  - `kd chat --new` — creates fresh thread
  - `kd chat <thread-id>` — opens specific thread by ID
  - If no current thread and no `--new`, show recent threads and offer to create one
- User types at bottom, plain text broadcasts to all council members by default
- `@member` addressing for directed messages, `@all` explicit broadcast
- When resuming a thread, show full history (all messages in sequence order)
- Pick up in-flight stream files if a `kd council ask --async` is running on the same thread

#### Input handling
- **Enter** sends the message (like Slack, Discord, other chat TUIs)
- **Shift+Enter** inserts a newline for multi-line input
- **Escape** sends interrupt signal: cancels all currently-generating agents **launched by this TUI process** (kills subprocesses via stored `self.process` handles), prevents new auto-turns from scheduling. Does not affect queries launched by other processes (e.g., `kd council ask` in another terminal).
- Input area grows to accommodate multi-line text (up to a reasonable max)

#### Slash commands (session-scoped, not persisted)
- `/mute <member>` and `/unmute <member>` — **skips** the member in queries (saves tokens), not just hides output. Session-scoped, resets when TUI closes.
- `/help` — show available commands and keybindings
- `/quit` or `/exit` — clean shutdown (waits for current generation if any, or kills on second Escape)

#### Streaming display
- Responses appear **inline in the message log** as they stream (not in a separate area)
- Each member's in-progress response shows as a growing panel with a streaming indicator
- Extract `text_delta` text from NDJSON lines for readable prose during streaming
- When the finalized message file lands, replace the streamed preview with the parsed response rendered as Markdown
- Members waiting to respond show a "waiting..." indicator in the log

#### Error display
- When a member errors or times out, show an inline error panel (red/yellow) with the error message
- Offer contextual hint: "Use /retry to re-query failed members" (future: implement /retry)

#### State and persistence
- All state persists to standard thread files — crash-safe, `kd council show` compatible
- The TUI is a view+input layer over thread files. **Conversation state** (messages, thread metadata) lives in thread files only. **Ephemeral UI state** (mute list, scroll position, in-progress subprocess handles) is TUI-process-scoped and resets on close — this is expected and fine.
- Stream file finalization signal: **finalized message file exists** (not stream file deletion, since deletion also happens during retries)

#### Dependencies
- Textual in `[dependency-groups] chat` (already added: `uv add --group chat textual`)
- `kd chat` shows install hint if textual not importable: `uv sync --group chat`
- Import textual lazily — only when `kd chat` is invoked

#### Query path
- The TUI manages `Council` and `CouncilMember` instances directly (via `Council.create()`), not by shelling out to `kd council ask`
- On user message: TUI writes the king message to thread files, then launches `member.query()` calls via `asyncio.to_thread()` (one per member for broadcast, sequential for auto-turns)
- This reuses existing orchestration (config loading, agent resolution, thread message writing) while giving the TUI direct access to subprocess handles for cancellation
- Agent availability errors (missing CLI) surface as `FileNotFoundError` from `query_once()` → rendered as error panels in the message log. No separate pre-flight check needed.

#### Async bridge
- Bridge Textual's asyncio event loop to blocking `member.query()` via `asyncio.to_thread()`
- Subprocess handle stored as `self.process` on `CouncilMember` (set inside `query_once()` after `Popen`). TUI calls `member.process.terminate()` on Escape.
- Also write PID to `AgentState` via `update_agent_state(..., pid=process.pid)` immediately after `Popen` — enables external monitoring even if the TUI crashes.

### Phase 2: Group chat mode

#### Auto-turns
- After initial broadcast round (parallel), councillors enter auto-mode (sequential round-robin)
- Auto-turns are sequential within a round (one member at a time) for predictable message ordering
- Round-robin order follows the `council.members` list order from config.json (user-controllable)
- Stop conditions: `auto_rounds` reached (hard cap, simple and predictable)
- **Escape interrupts auto-mode**: kills currently-generating agent, prevents next auto-turn from scheduling. User's next message resumes normal flow.

#### Thread history injection
Each auto-turn builds a prompt containing the **full thread history** formatted as a multi-party conversation. This replaces session resume for cross-agent awareness since `--resume` only carries single-agent context.

**History format:**
```
[Previous conversation]
king: What should we do about X?

claude: I think we should consider three approaches...

codex: I disagree because...

cursor: Building on what claude said...

---
You are cursor. Continue the discussion. Respond to the points raised above.
```

- Thread history is constructed from finalized message files in sequence order
- The preamble (safety + phase + agent prompts) is prepended before the history block
- The history block only contains message bodies, not preambles or instructions
- Each member is identified by name, matching the `from` field in message frontmatter

#### Context management
- **All context goes in by default** — send the full thread history with every auto-turn
- When context gets too large for an agent's window, the **king notices** (the human user) and starts a new chat thread, possibly with a summary of the prior conversation
- No automatic truncation or summarization in Phase 2 — keep it simple. The human manages context boundaries.

#### Config (flat keys under `council` in config.json)
- `council.auto_rounds`: max rounds without user input (default 3, positive int)
- `council.mode`: `"broadcast"` (first round parallel, then sequential auto-turns) or `"sequential"` (round-robin from the start). Default: `"broadcast"`.

Add `auto_rounds`, `mode`, and `preamble` to `VALID_COUNCIL_KEYS` in `config.py`. Flat keys match the existing `council.members` / `council.timeout` pattern — no nested `chat` object.

**Config JSON shape and validation:**
```json
{
  "council": {
    "members": ["claude", "codex", "cursor"],
    "timeout": 600,
    "auto_rounds": 3,
    "mode": "broadcast",
    "preamble": "You are a council advisor to the King. ..."
  }
}
```

| Key | Type | Default | Validation |
|-----|------|---------|------------|
| `auto_rounds` | int | `3` | Must be positive (> 0) |
| `mode` | str | `"broadcast"` | Must be one of: `"broadcast"`, `"sequential"` |
| `preamble` | str | current `COUNCIL_PREAMBLE` text | Non-empty string |

Update `CouncilConfig` dataclass to include these three fields with defaults. Unknown keys continue to raise `ValueError` (existing behavior).

#### Round/turn tracking
- Current `thread_response_status()` only tracks responses to the latest king message — doesn't fit member-to-member auto-turns
- Need explicit round/turn metadata: either persist round markers in thread state, or infer rounds from message sequence (messages between king messages form a round)
- Decision: infer from message ordering. A "round" is a complete cycle of all (unmuted) members responding. King messages reset the round counter. Simple, no new metadata format.
- **Edge cases**: `@member` directed messages don't count as a broadcast round — only the addressed member responds, no round counter increment. `/mute`-ed members are excluded from expected responders for that round. If a member errors or times out, skip them for that round (the round completes with the remaining members). Retries don't create duplicate round entries — a retry replaces the errored response at the same sequence position.

### Phase 3: Configurable preamble

The hardcoded `COUNCIL_PREAMBLE` in `CouncilMember` restricts agents to read-only advisory. For the "best engineers" chat experience, users should be able to customize this.

- Move preamble to config: `council.preamble` key in `config.json`
- Default value: current `COUNCIL_PREAMBLE` text (backward compatible)
- Per-agent customization via existing `agents.<name>.prompts.council` — this is **additive** (appended after the preamble), not a replacement. To fully override the preamble for one agent, set `council.preamble` globally and use the agent's `prompts.council` to add agent-specific instructions on top.
- Prompt merge order stays: preamble + phase prompt + agent prompt + user prompt (or thread history)
- Add `preamble` to `VALID_COUNCIL_KEYS` in `config.py` alongside `auto_rounds` and `mode`

## TUI Architecture

### Layout

```
┌──────────────────────────────────────────────────────┐
│  kd chat · thread-a8b3 · claude codex cursor         │  ← Header (static)
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌ king ────────────────────────────────────────── ┐ │
│  │ What should we do about the database schema?    │ │
│  └──────────────────────────────────────────────── ┘ │
│                                                      │
│  ┌ claude (streaming · 2,847 chars) ─────────────  ┐ │  ← Color-coded
│  │ I think we should consider three approaches:    │ │     by member
│  │                                                 │ │
│  │ 1. Normalize fully and use joins...             │ │
│  │ 2. Denormalize for read performance...          │ │
│  │ ▍                                               │ │  ← Cursor while
│  └──────────────────────────────────────────────── ┘ │     streaming
│                                                      │
│  ┌ codex ──────── waiting... ──────────────────── ┐ │
│  └──────────────────────────────────────────────── ┘ │
│                                                      │
│  ┌ cursor ─────── waiting... ──────────────────── ┐ │
│  └──────────────────────────────────────────────── ┘ │
│                                                      │  ← Scrollable
├──────────────────────────────────────────────────────┤     message log
│  Esc: interrupt · Enter: send · Shift+Enter: newline │  ← Status bar
├──────────────────────────────────────────────────────┤
│  > your message here                                 │  ← Input (grows
│    second line of multi-line input                   │     with content)
└──────────────────────────────────────────────────────┘
```

### Widget tree (Textual)

```
ChatApp(App)
├── Header         — Static: thread ID, member names
├── MessageLog     — VerticalScroll container
│   ├── MessagePanel(Static)    — Rendered king message (Rich Markdown)
│   ├── MessagePanel(Static)    — Rendered finalized response (Rich Markdown)
│   ├── StreamingPanel(Static)  — In-progress response (updates as tokens arrive)
│   ├── WaitingPanel(Static)    — "waiting..." placeholder
│   └── ErrorPanel(Static)      — Red panel for errors/timeouts
├── StatusBar      — Static: keybinding hints, auto-round status
└── InputArea      — TextArea widget (Shift+Enter = newline, Enter = send via key binding)
```

### Rendering

- **Finalized messages**: Render body as Rich Markdown inside a bordered panel. Panel border color assigned per member (consistent across session). King messages use a distinct style (no border or different border).
- **Streaming messages**: Same panel structure, but body updates every poll cycle. Show `(streaming · N chars)` in panel title. Append `▍` cursor at end of text. On finalization, re-render as full Markdown.
- **Waiting placeholders**: Collapsed panel with `waiting...` in title. Expands when streaming starts. In broadcast mode, create WaitingPanels for all members immediately when the user sends a message. In sequential auto-turns, show a WaitingPanel for the next member preemptively so the user knows more is coming.
- **Errors**: Red-bordered panel with error text. Title shows `errored` or `timed out`.
- **Code blocks**: Textual's Markdown widget handles syntax highlighting via Rich. No special handling needed.

### Polling and updates

- Poll at **100ms** in the Textual async loop (`set_interval(0.1, poll_updates)`)
- Each poll cycle:
  1. Check for new finalized message files (sequence > last known)
  2. Read new bytes from `.stream-{member}.jsonl` files (track byte offset per member)
  3. Extract text deltas, append to in-progress panel
  4. If finalized message appeared for a streaming member, replace StreamingPanel with MessagePanel
- Textual batches DOM updates automatically — 100ms polls won't cause flicker
- **Auto-scroll**: scroll to bottom when new content arrives, but only if the user is already at the bottom. If the user has scrolled up to re-read, don't yank them back.

### Module structure

```
src/kingdom/tui/
├── __init__.py    — Lazy import guard, install hint
├── app.py         — ChatApp(App) main class, screen layout, keybindings
├── widgets.py     — MessagePanel, StreamingPanel, WaitingPanel, ErrorPanel
└── poll.py        — File polling logic, stream text extraction, thread state tracking
```

`cli.py` gets a thin `kd chat` command that imports from `kingdom.tui` and launches the app.

## Relationship: `kd chat` and `kd council ask`

Both operate on the same thread files. They are interoperable:

- **`kd council ask` then `kd chat`**: TUI shows full history including CLI-initiated messages. If async queries are still in flight, TUI picks up their stream files.
- **`kd chat` then `kd council ask`**: CLI sees messages sent from the TUI. `kd council show` renders them normally.
- **Concurrent use**: Both can be open on the same thread for reading. Messages use exclusive-create for sequence numbers, so concurrent writes are safe. However, **concurrent queries to the same member on the same thread will conflict** — stream files are `.stream-{member}.jsonl` (per-member, not per-request) and get deleted on completion/retry. Mitigation: don't query the same member from two processes simultaneously. The TUI should detect in-flight stream files from external queries and show them as read-only streaming panels rather than launching duplicate queries.
- **Different threads**: `kd chat` and `kd council ask` can target different threads simultaneously. No interference.

This is a natural consequence of the file-based architecture. No special handling needed.

## Non-Goals

- No TUI inside Claude Code's terminal — accept the separate pane
- No tmux-as-transport — tmux is just a viewport convenience
- No complex activation strategies (natural order, talkativeness scoring) — round-robin is enough
- No anonymization (Karpathy-style) — we know which model is which
- No token/cost budgeting per round — just cap turn count
- No complex stream normalization — extract `text_delta` text with trivial per-line JSON parsing
- No `kd council review` — separate feature
- No changes to peasant worker streaming — defer to later PR
- No automatic context truncation or summarization — the king manages context boundaries manually
- No `/retry` command in Phase 1 — show the hint but implement later

## Decisions

- **Textual over Rich Live**: Textual gives us scrollable panels, proper input widget, layout management, and async-native architecture. Rich Live + prompt_toolkit would be lighter but we'd reinvent half of Textual. Kingdom already depends on Rich; Textual is a natural step up.
- **Textual as dependency group**: `[dependency-groups] chat` in pyproject.toml. Install with `uv sync --group chat`. Lazily imported only when `kd chat` is invoked. Show install hint if missing.
- **File polling at 100ms**: Fast enough for smooth token streaming in the TUI. Textual batches DOM updates. No watchdog/inotify complexity.
- **Thread files as single source of truth**: The TUI reads/writes the same thread directory as `kd council show/ask`. No separate state. Crash-safe. Fully interoperable.
- **Thread-scoped context, not agent-scoped sessions**: For group chat, context comes from thread history injection, not per-agent `--resume`. This ensures all members see the full multi-party conversation. Session resume carries only single-agent context and would duplicate the agent's own messages.
- **Finalized message file = "done" signal**: Don't rely on stream file deletion to detect finalization (deletion also happens during retries). Check for the existence of a finalized `NNNN-{member}.md` file instead.
- **Group chat is round-robin with hard cap**: Each member responds once per round, sequential within a round, up to N rounds. User can interrupt. Simple.
- **Round inference from message ordering**: A "round" is a complete cycle of all unmuted members. King messages reset. No new metadata format needed.
- **Stream files are `.jsonl`, not `.md`**: Ephemeral machine-readable artifacts consumed by watch/TUI. Finalized messages stay as `.md`.
- **`kd chat` is the command name**: Top-level command, not a council subcommand.
- **Enter sends, Shift+Enter newlines**: Matches Slack, Discord, and other chat TUIs. Engineer-friendly multi-line input via Shift+Enter.
- **Escape interrupts all agents**: Kills currently-generating subprocesses and prevents new auto-turns. Second Escape during `/quit` forces immediate exit.
- **Inline streaming display**: Responses appear in the message log as growing panels (not a separate streaming area). Feels like real chat — messages appear where they'll live permanently.
- **Configurable preamble**: Move `COUNCIL_PREAMBLE` to `council.preamble` config key. Default to current text. Per-agent `agents.<name>.prompts.council` is additive on top (not a replacement).
- **All context by default**: Send full thread history in every auto-turn prompt. No truncation. When context fills up, the king starts a new thread manually.
- **`/mute` skips, not hides**: Muting a member excludes them from queries (saves tokens). Session-scoped — resets when TUI closes.
- **Config-driven group chat**: `council.auto_rounds` and `council.mode` as flat keys in `config.json` (matches existing pattern).
- **Separate `kingdom/tui/` module**: cli.py is already large. TUI code lives in its own package.
- **Thread-history-only, no session resume**: Drop `--resume` for group chat entirely. Council is read-only advisory — tool-use context across turns has near-zero value. Thread history injection provides full cross-agent awareness without duplicating the agent's own messages.
- **Subprocess cancellation via `self.process`**: Store the `Popen` handle as `self.process` on `CouncilMember` (set inside `query_once()`). TUI calls `member.process.terminate()` on Escape. Also write PID to `AgentState` for external monitoring. Simplest approach — no file-based PID lookup races, no new async query method.

## Open Questions

- **Cursor token-level streaming**: Does Cursor's `agent` CLI have `--include-partial-messages` equivalent? If not, streaming will be per-turn rather than token-level — still a big improvement.
- **Member colors**: Should member panel colors be configurable in `config.json`, or hardcoded per-member based on name hash? Hardcoded is simpler for Phase 1.

---

## Council Thread: council-a8ba

(Council responses preserved in thread files for reference.)
