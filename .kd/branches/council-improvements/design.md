# Design: council-improvements

## Goal

Make council interactions feel natural and alive. Fix all existing bugs/UX issues with the CLI-based council workflow (the "inside Claude Code" path), then build a dedicated `kd chat` TUI as a sidecar for rich, streaming, multi-agent group chat.

## Context

The council today works but feels dead. You send a message, wait 4 minutes behind a spinner, then get 3 walls of text dumped at once. The `.stream-{member}` files already capture live output during execution, but `watch_thread()` ignores them entirely — it only polls for finalized message files. The async error handling is brittle (silent `Error: None`, no retry, `reset` nukes everything). Status reporting is binary (pending/responded) when reality has more states (running, errored, timed out, interrupted).

Beyond CLI fixes, we want a `kd chat` TUI that runs in a separate terminal pane alongside Claude Code. It should feel like a Slack thread with three engineers: you send a message, see responses stream in with color-coded panels, and optionally let the councillors discuss amongst themselves with bounded auto-turns.

The thread/messaging system we built since the last TUI attempt is the key enabler — the TUI becomes a pure view+input layer over thread files, not a stateful monolith.

### Streaming reality

Investigation of current agent output modes and the tee logic in `CouncilMember.query()` (`base.py:82-131`):

The tee mechanism: a daemon thread reads subprocess stdout line-by-line, appends each line to `stdout_lines` list, and if `stream_path` is set, writes the line to `.stream-{member}.jsonl` and flushes immediately. After process exit, all lines are joined and passed to the backend-specific `parse_response()`.

**Per-backend behavior (current — `--output-format json`):**

| Backend | CLI flags | Stdout format | Stream file during execution | Stream file usefulness |
|---------|-----------|--------------|------------------------------|----------------------|
| **Claude Code** | `claude --print --output-format json` | Single JSON blob at end | Partial JSON fragments (`{"result":"Here is my ana...`) | **Useless.** Not parseable or readable until process exits. |
| **Codex** | `codex exec --json` | JSONL events, one per line, streamed incrementally | Complete JSON events per line (`{"type":"item.completed",...}`) | **Machine-readable** but raw JSON, not prose. |
| **Cursor** | `agent --print --output-format json` | Single JSON blob at end | Same as Claude Code — partial JSON fragments | **Useless.** Same problem as Claude. |

**Streaming investigation results (confirmed Feb 14, 2026):**

Both Claude Code and Cursor support `--output-format stream-json` which emits NDJSON (one JSON object per line, streamed as events arrive). This completely solves the streaming problem.

**Claude Code — token-level streaming confirmed:**
- Flags: `claude --print --output-format stream-json --verbose --include-partial-messages`
- `--output-format stream-json` emits NDJSON with per-turn events (tool calls, completed messages)
- Adding `--include-partial-messages` enables **token-level** `text_delta` events
- Each delta is a complete, parseable JSON line: `{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}}`
- Text extraction: `jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'`
- Session ID extractable from the final result event
- Format changed in v0.2.120 to use `.message.content` structure for completed messages
- Sources: [CLI reference](https://code.claude.com/docs/en/cli-reference), [headless docs](https://code.claude.com/docs/en/headless), [issue #733](https://github.com/anthropics/claude-code/issues/733)

**Cursor — streaming confirmed, partial-message flag unverified:**
- Flags: `agent --print --output-format stream-json`
- Emits NDJSON with event types: system init, deltas, tool calls, result
- Event format differs from Claude Code (uses `user`/`assistant`/`tool_call`/`result` types)
- Whether a `--include-partial-messages` equivalent exists is unconfirmed — needs hands-on testing
- Even without token-level deltas, `stream-json` emits events per tool call and per message completion, which is far better than current single-blob behavior
- Sources: [tarq.net stream format post](https://tarq.net/posts/cursor-agent-stream-format/), [Cursor CLI docs](https://www.everydev.ai/tools/cursor-cli)

**Codex — already streams JSONL natively.** No changes needed.

**Per-backend behavior (with stream-json):**

| Backend | CLI flags | Stream file usefulness |
|---------|-----------|----------------------|
| **Claude Code** | `--output-format stream-json --verbose --include-partial-messages` | **Excellent.** Token-level NDJSON, each line parseable. Readable text extractable via `text_delta` events. |
| **Codex** | `--json` (unchanged) | **Good.** JSONL events as before. |
| **Cursor** | `--output-format stream-json` | **Good to excellent.** NDJSON events per turn; token-level TBD pending testing. |

**Implication:** The core UX blocker is not backend capability — it's our command/parsing path being pinned to `--output-format json`. Switching to `stream-json` for council queries makes `.stream-{member}.jsonl` files genuinely useful for live display.

**Implementation direction:**
- **Switch council command builders** to use `stream-json` mode for Claude and Cursor (keep `json` mode available for non-streaming paths if needed, but council always wants streaming).
- **Write NDJSON stream parsers** that extract incremental text from backend-specific event formats. The tee mechanism in `base.py` already writes line-by-line — with NDJSON each line is a complete JSON object.
- **Update `parse_response()`** to handle NDJSON (join all text deltas, extract session_id from result event) for the final response after process exit.
- **Stream file consumers** (`watch_thread()`, TUI) can parse `.stream-{member}.jsonl` line-by-line, extract `text_delta` text, and display readable prose in real time.

**Current parse functions** (all in `agent.py`):
- `parse_claude_response()` (line 101): `json.loads(stdout)` on entire string, expects `{"result": "...", "session_id": "..."}`
- `parse_codex_response()` (line 120): Splits on newlines, parses each line as JSON event, extracts `item.completed` text
- `parse_cursor_response()` (line 155): `json.loads(stdout)` on entire string, tries keys `result`/`text`/`response`

All three parsers need updating: Claude and Cursor switch from single-JSON to NDJSON parsing. Codex parser is already NDJSON-shaped but may need alignment with the common extraction interface.

## Requirements

### Phase 0: Foundations
These cross-cutting concerns must be resolved before Phase 1-3 work:
- **Switch council to stream-json mode**:
  - Claude: change `BACKEND_DEFAULTS` cli to `claude --print --output-format stream-json --verbose --include-partial-messages` (or add these flags in the council command builder path).
  - Cursor: change to `agent --print --output-format stream-json`. Test whether Cursor supports a `--include-partial-messages` equivalent for token-level deltas.
  - Codex: no change needed (already NDJSON).
  - Decision: whether to change `BACKEND_DEFAULTS` globally or add streaming flags only in the council path. Council always benefits from streaming; peasant workers may not need it (they use `--output-format json` for structured result parsing). Likely: add a `streaming=True` parameter to `build_command()` that appends stream-json flags.
- **Write NDJSON parsers** for Claude and Cursor that handle the full stdout as NDJSON after process exit (extract all text, session_id). These replace the current single-JSON parsers when streaming mode is active.
- **Write stream-line extractors** for real-time display: given a single NDJSON line from a `.stream-{member}.jsonl` file, extract the human-readable text fragment (if any). Backend-specific: Claude uses `text_delta` events, Cursor uses its own delta format, Codex uses `item.completed`.
- **Config schema extension**: Add `council.chat` and `council.auto_commit` to `config.json` schema. Update `VALID_COUNCIL_KEYS` in `config.py`, add `ChatConfig` dataclass + validation.
- **Verify/close stale tickets**: 41fb (`_print_thread_status`) — function is already `print_thread_status` with no underscore. Verify and close. 520a (research spike) — council responses already informed design. Close or move to backlog.
- **Clarify 549b (configurable members)**: `Council.create()` already reads `config.json` members list. This may already work — verify and close if so, or keep as hardening/documentation.

### Phase 1: Fix existing council CLI
- **Async error handling** (6412): Meaningful error messages (not `Error: None`), automatic retry (once with same session, once with session reset if first retry fails), per-member session reset (`kd council reset --member <name>`), `kd council retry <thread-id>` to re-query only failed members using original prompt from last king message. Retriable errors: timeout, non-zero exit. Non-retriable: command-not-found.
- **Richer status** (a9c9): Distinguish at least: responded, running, errored, timed out, pending. Derive "running" from worker PID liveness check (`os.kill(pid, 0)`). Derive "errored"/"timed out" from error field in response messages. Record worker PID in session state (already has `pid` field).
- **`council show` pagination** (70f6): Default to latest turn (last king message + all responses after it). `--last N` shows last N turns (not messages). `--all` shows full history. Show count of hidden messages/turns.
- **Visual turn separation** (d09d): Clear visual separators (horizontal rules, turn headers) between conversational turns in `council show`.
- **`council list` enrichment** (a4f5): Show per-member response status (responded/pending/errored) and first line of king's prompt as topic summary.
- **Auto-commit threads** (1e3d): After all members respond, auto-commit thread files. Runs in the worker process (works for both sync and async flows). Scoped to thread directory only (`git add .kd/branches/.../threads/<id>/`). Commit message: `council: <truncated prompt>`. Controlled by `council.auto_commit` config (default: true). No prompting — incompatible with async mode. No commit if no diff.
- **Stream file display in watch**: Update `watch_thread()` to tail `.stream-{member}.jsonl` files alongside polling for finalized messages. With stream-json mode, each line is a complete NDJSON object — extract `text_delta` text for readable prose display. Show accumulated text that grows as tokens arrive. Replace with the final rendered response when the message file lands.

### Phase 2: `kd chat` TUI
- Dedicated Textual app, runs in a separate terminal pane
- Opens existing thread or creates new one (`kd chat` resumes current thread, `kd chat --new` creates fresh)
- User types at bottom, plain text broadcasts to all council members by default
- `@member` addressing for directed messages, `@all` explicit broadcast
- Small set of slash commands for session control (not config):
  - `/mute <member>` and `/unmute <member>` — session-scoped, dies when TUI closes
  - `/help` — show available commands
  - `/quit` or `/exit`
- Responses stream into color-coded panels by tailing `.stream-{member}.jsonl` files
- Extract `text_delta` text from NDJSON lines for readable prose display during streaming. When the finalized message file lands, replace the streamed text with the parsed response.
- All state persists to standard thread files — crash-safe, `kd council show` compatible
- Textual as optional dependency (`uv add --optional tui textual`). `kd chat` shows install hint if not available.
- Bridge Textual's asyncio event loop to blocking subprocess queries via `asyncio.to_thread()`
- Handle `.stream-{member}.jsonl` deletion gracefully (file disappearing = message finalized, switch to thread message file)

### Phase 3: Group chat mode
- After initial broadcast round (parallel), councillors enter auto-mode (sequential round-robin)
- **Thread history injection**: Each auto-turn builds a prompt containing the full thread history formatted as a multi-party conversation, not relying on session resume (which only carries single-agent context). New logic needed in `build_command()` or a new method.
- All group chat behavior configured in `config.json` under `council.chat`:
  - `auto_rounds`: max rounds without user input (default 3)
  - `mode`: `"broadcast"` (first round parallel, then sequential auto-turns) or `"sequential"` (round-robin from the start)
- User typing interrupts auto-mode: stops scheduling new turns, user's message sent after current generation completes (don't kill mid-generation)
- Auto-turns are sequential within a round (one member at a time) to maintain predictable message ordering
- Stop conditions: max rounds reached. Drop the "short/empty response" heuristic — just use the hard cap. Simple and predictable.

## Non-Goals
- No TUI inside Claude Code's terminal — accept the separate pane
- No tmux-as-transport — tmux is just a viewport convenience
- No complex activation strategies (natural order, talkativeness scoring) — round-robin is enough
- No anonymization for now (Karpathy-style) — we know which model is which
- No token/cost budgeting per round — just cap turn count
- No complex stream normalization — but DO extract `text_delta` text from NDJSON lines for readable display (this is trivial per-line JSON parsing, not "normalization")
- No `kd council review` in this PR (1c4b) — separate feature
- No research spike ticket (520a) — council responses already informed design

## Decisions

- **Textual over Rich Live**: Textual gives us scrollable panels, proper input widget, layout management, and async-native architecture. Rich Live + prompt_toolkit would be lighter but we'd reinvent half of Textual. Kingdom already depends on Rich; Textual is a natural step up. Add as optional dependency.
- **File polling over events**: Poll `.stream-*.jsonl` and message files at 250ms. LLM responses take seconds; sub-100ms latency doesn't matter. No watchdog/inotify.
- **Thread files as single source of truth**: The TUI reads/writes the same thread directory as `kd council show/ask`. No separate state. Crash-safe.
- **Group chat is round-robin with hard cap**: Each member responds once per round, sequential within a round, up to N rounds. User can interrupt. Simple.
- **Stream files are `.jsonl`, not `.md`**: Stream files are ephemeral machine-readable artifacts (NDJSON lines consumed by watch/TUI), not human-readable documents. Finalized messages stay as `.md`. The dotfile prefix (`.stream-`) already signals "internal" — the `.jsonl` extension makes the contract honest.
- **Lightweight stream parsing, not raw display**: With stream-json mode, each line in `.stream-{member}.jsonl` is a complete JSON object. Extract `text_delta` text for readable prose display during streaming. This is trivial per-line `json.loads()` + key access, not complex normalization. On completion, the finalized parsed response replaces the streamed text. Raw NDJSON fallback if a line doesn't parse.
- **`kd chat` is the command name**: Top-level command, not a council subcommand.
- **Config-driven group chat**: Auto-rounds, mode live in `config.json`. Minimal TUI commands: `@member`, `@all`, `/mute`, `/unmute`, `/help`, `/quit`.
- **Auto-commit in worker process**: After all responses land, worker does scoped `git add` + `git commit` on the thread directory. Config-controlled.
- **Interrupt = queue, not kill**: User typing during auto-mode stops new turns from being scheduled. Current generation completes. User's message sent after.
- **Thread history injection for group chat**: Auto-turns build full thread context into the prompt. Don't rely on session resume for cross-agent awareness.

## Open Questions
- **Cursor token-level streaming**: Does Cursor's `agent` CLI have an equivalent to `--include-partial-messages`? Needs hands-on testing. If not, streaming will be per-turn (tool call/message boundaries) rather than token-level — still a big improvement over current single-blob.
- **Streaming scope**: Should `kd council ask` (non-watch, non-TUI) also switch to stream-json? Pro: consistent behavior, stream files always useful. Con: slightly more parsing complexity for the simple "ask and wait" path. Leaning toward: yes, always use stream-json for council — the parser handles both modes and stream files become universally useful.
- **Peasant workers**: Should peasant `build_command()` also gain a streaming option? Less urgent — peasants don't have a live-display path today. Defer to a later PR.

---

## Council Thread: council-f30b

(Council responses preserved below for reference — see thread files for full text.)
