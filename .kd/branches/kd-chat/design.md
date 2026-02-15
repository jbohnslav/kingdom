# Design: kd-chat

## Goal

Build a dedicated `kd chat` TUI as a sidecar for rich, streaming, multi-agent group chat. Runs in a separate terminal pane alongside Claude Code. Feel like a Slack thread with three engineers: you send a message, see responses stream in with color-coded panels, and optionally let the councillors discuss amongst themselves with bounded auto-turns.

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
- Config schema with `council.chat` and `council.auto_commit` keys

## Requirements

### Phase 1: `kd chat` TUI

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

### Phase 2: Group chat mode

- After initial broadcast round (parallel), councillors enter auto-mode (sequential round-robin)
- **Thread history injection**: Each auto-turn builds a prompt containing the full thread history formatted as a multi-party conversation, not relying on session resume (which only carries single-agent context). New logic needed in `build_command()` or a new method.
- All group chat behavior configured in `config.json` under `council.chat`:
  - `auto_rounds`: max rounds without user input (default 3)
  - `mode`: `"broadcast"` (first round parallel, then sequential auto-turns) or `"sequential"` (round-robin from the start)
- User typing interrupts auto-mode: stops scheduling new turns, user's message sent after current generation completes (don't kill mid-generation)
- Auto-turns are sequential within a round (one member at a time) to maintain predictable message ordering
- Stop conditions: max rounds reached. Just use the hard cap. Simple and predictable.

## Non-Goals

- No TUI inside Claude Code's terminal — accept the separate pane
- No tmux-as-transport — tmux is just a viewport convenience
- No complex activation strategies (natural order, talkativeness scoring) — round-robin is enough
- No anonymization (Karpathy-style) — we know which model is which
- No token/cost budgeting per round — just cap turn count
- No complex stream normalization — extract `text_delta` text with trivial per-line JSON parsing
- No `kd council review` — separate feature
- No changes to peasant worker streaming — defer to later PR

## Decisions

- **Textual over Rich Live**: Textual gives us scrollable panels, proper input widget, layout management, and async-native architecture. Rich Live + prompt_toolkit would be lighter but we'd reinvent half of Textual. Kingdom already depends on Rich; Textual is a natural step up. Add as optional dependency.
- **File polling over events**: Poll `.stream-*.jsonl` and message files at 250ms. LLM responses take seconds; sub-100ms latency doesn't matter. No watchdog/inotify.
- **Thread files as single source of truth**: The TUI reads/writes the same thread directory as `kd council show/ask`. No separate state. Crash-safe.
- **Group chat is round-robin with hard cap**: Each member responds once per round, sequential within a round, up to N rounds. User can interrupt. Simple.
- **Stream files are `.jsonl`, not `.md`**: Stream files are ephemeral machine-readable artifacts consumed by watch/TUI. Finalized messages stay as `.md`.
- **Lightweight stream parsing, not raw display**: Extract `text_delta` text from NDJSON for readable prose during streaming. Finalized parsed response replaces streamed text on completion.
- **`kd chat` is the command name**: Top-level command, not a council subcommand.
- **Config-driven group chat**: Auto-rounds, mode live in `config.json`. Minimal TUI commands: `@member`, `@all`, `/mute`, `/unmute`, `/help`, `/quit`.
- **Interrupt = queue, not kill**: User typing during auto-mode stops new turns from being scheduled. Current generation completes. User's message sent after.
- **Thread history injection for group chat**: Auto-turns build full thread context into the prompt. Don't rely on session resume for cross-agent awareness.

## Open Questions

- **Cursor token-level streaming**: Does Cursor's `agent` CLI have `--include-partial-messages` equivalent? If not, streaming will be per-turn rather than token-level — still a big improvement.
- **Config schema for chat**: What additional `council.chat` keys might be needed beyond `auto_rounds` and `mode`? Member colors? Display width?
