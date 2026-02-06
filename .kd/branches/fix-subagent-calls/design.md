# Design: Subagent Visibility & Debugging

## Goal

When Kingdom spawns subagents (council members, future peasants), provide real-time visibility into what they're doing — similar to the interactive feel of running a coding agent directly.

## Problem

Currently `kd council ask` uses `subprocess.run()` which blocks until completion. The user sees a spinner for minutes with no idea:
- Whether the agent started
- What it's working on
- Whether it's stuck or making progress
- What tool calls / file edits are happening

This makes debugging impossible and the UX feels broken even when it's working.

## What Visibility Would Help

1. **Agent started** — confirmation the subprocess launched
2. **Incremental output** — text arriving as the agent thinks/responds
3. **Activity indicators** — tool calls, file operations, "thinking"
4. **Stuck detection** — distinguish "working" from "hung"
5. **Error surfacing** — see failures as they happen, not after timeout

## Design Options

### A. Stream subprocess output directly

Use `Popen` with line-by-line reads, print to terminal as output arrives.

- **Pros**: Simple, immediate visibility, no extra infrastructure
- **Cons**: Multiple agents interleave messily, hard to read
- **Variant**: Prefix each line with agent name `[claude] ...`

### B. Per-member log files with live tailing

Write each member's output to a file. Show Rich Live display with summary stats ("claude: 47 lines, codex: 23 lines, agent: waiting..."). User can `tail -f` individual logs.

- **Pros**: Clean separation, full history, debuggable after the fact
- **Cons**: Extra files, user has to open another terminal to see details
- **Variant**: `--verbose` flag streams one selected member to terminal

### C. tmux/screen sessions

Each subagent runs in its own tmux pane or window. User can attach and watch.

- **Pros**: Full visibility, can interact if needed, works on remote servers
- **Cons**: Requires tmux, more complex orchestration, session cleanup
- **Variant**: Single tmux window with split panes for all members

### D. Hybrid approach

Default: summarized progress in terminal (lines received, elapsed time, status).
Flags for more visibility:
- `--stream <member>` — stream one member's output live
- `--attach` — open tmux session to watch all
- `--verbose` — show all output interleaved with prefixes

- **Pros**: Good defaults, power-user options available
- **Cons**: More code paths to maintain

## Implementation Considerations

- `subprocess.Popen` with `stdout=PIPE` and non-blocking reads
- Threading or asyncio to handle multiple streams
- Rich Live display for updating progress without scroll spam
- Log files written regardless of display mode (for debugging)
- Timeout handling that can interrupt stuck processes

## Broader Applicability

This same pattern applies to:
- **Council queries** — current pain point
- **Peasant execution** — future autonomous workers
- **Any CLI-spawned agent** — unified visibility model

Whatever we build should work for all of these.

## Open Questions

1. Should streaming be opt-in (`--stream`) or default?
2. How do we handle 3+ agents outputting simultaneously without chaos?
3. Do we need tmux, or is log files + optional streaming enough?
4. Should there be a web UI for monitoring? (future scope)
5. How does this interact with `--json` output mode?
