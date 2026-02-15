---
from: claude
to: king
timestamp: 2026-02-15T00:08:49Z
---

Now I have a comprehensive understanding. Here's the review.

---

## Design Review: council-improvements

### 1. Contradictions and Internal Inconsistencies

**The /mute /unmute problem (your question #9).** The doc says two contradictory things:

- Phase 2 Requirements: "`/mute` and `/unmute` per member"
- Non-Goals: "No slash commands for config — configure via `config.json`, not the TUI"
- Decisions: "The TUI input is just for talking: plain text goes to all, `@member` goes to one"

These can't all be true. Mute/unmute is inherently runtime state — you don't want to edit `config.json` mid-conversation to silence codex for two turns. My recommendation: **mute/unmute should exist but as `@mute codex` and `@unmute codex`**, keeping the `@` prefix convention consistent with `@member` addressing. This avoids introducing a separate `/` namespace while still being discoverable. It's not "config" — it's session state that dies when you close the TUI.

**Ticket 41fb (rename `_print_thread_status`).** Looking at `cli.py:690`, the function is already called `print_thread_status` — no underscore prefix. Either this ticket was already done and not closed, or the design doc is referencing a stale ticket. Either way, it shouldn't be in the Phase 1 requirements list. Verify and close it.

**Ticket 520a (research spike) is listed as non-goal but is also an open ticket on this branch.** The design doc says "No research spike (520a) — council responses already informed the design." That's fine, but the ticket is still `open` in `.kd/branches/council-improvements/tickets/520a.md`. Close it or move it to backlog so `kd done` doesn't block you.

### 2. Phase 1 Completeness and Missing Details

**Async error handling (6412) — retry semantics are underspecified.** The doc says "automatic retry (at least once)" but doesn't address:
- When does the retry happen? Immediately after failure, or after all members complete?
- Does the retry use the same session_id? If the failure was a session corruption issue, retrying with the same session will fail again. You probably want: retry once with same session, then retry once with session reset.
- What constitutes a retriable error? Currently `response.error` can be timeout, command-not-found, exit-code-nonzero, or parse failure. Timeout should retry. Command-not-found should not. Exit-code-nonzero depends on the error.
- The `kd council retry <thread-id>` command: does it re-query with the original prompt? Where does it find the prompt — from the thread's last king message? What if the prompt contained `@mentions` that filtered the member list?

Look at `council/council.py:115-130` — when a future raises an exception, it creates an error response and writes it to the thread. A retry command needs to detect these error messages in the thread, extract the original prompt from the king message, and re-dispatch only to failed members. This is doable but the design should specify it.

**Richer status (a9c9) — "derived from process state and log files" is vague.** The current `thread_response_status()` in `thread.py:340` only looks at message files. To show "running" vs "errored" vs "timed out", you need to either:
1. Check if the worker subprocess is still alive (PID in session state — `session.py:39` already has a `pid` field)
2. Parse the last log entry from `council-{member}.log` for error/timeout markers
3. Add a status field to the stream files (`.stream-{member}.md`)

Option 1 is the most reliable. The worker already runs as a detached subprocess (`start_new_session=True`). If you record its PID, you can `os.kill(pid, 0)` to check liveness. But note: the current worker spawns *all* members in one process via `query_to_thread()`. To get per-member PID tracking, you'd need to either spawn one worker per member or have the single worker report per-member status. The design should specify which approach.

**Configurable members (549b) — already works.** Looking at `council.py:36-38`, `Council.create()` already reads `cfg.council.members` and only includes listed agents. The ticket title says "Allow council to run with Claude Code and exclude Codex" — this is just a config.json change: `"members": ["claude", "cursor"]`. Unless there's a CLI override (`kd council ask --members claude,cursor`) that's missing? The design should clarify what's actually broken vs. what's just documentation.

**`council show` pagination (70f6) — missing detail on "latest turn."** The design says "Default to latest turn (last king message + responses)." But what counts as a turn in a multi-round thread? If you've had 3 rounds of conversation, does `council show` default to showing only the last round? That's probably right, but the `--last N` flag is ambiguous: does N mean "last N messages" or "last N turns (king ask + all responses)"? Turns would be more useful.

**Auto-commit (1e3d) — your question #10.** The ticket has empty acceptance criteria. Here's what I'd recommend:

The council writes files to `.kd/branches/<branch>/threads/<id>/`. These are git-tracked. Currently the user has to manually `git add` and `git commit` these thread files, which is easy to forget (violating the "commit `.kd/` changes as you go" principle from MEMORY.md).

Options:
- **Auto-commit silently after all members respond**: `git add .kd/branches/.../threads/<id>/ && git commit -m "council: <first-line-of-prompt>"`. Simplest, but noisy commit history.
- **Auto-commit after each response arrives**: Even noisier. Don't do this.
- **Prompt after all members respond**: `kd council ask` finishes, then prints "Commit thread? [Y/n]" — but this breaks the `--async` flow where the CLI exits before responses arrive.
- **Auto-commit in the worker process**: The async worker (`worker.py`) already runs detached. After `c.query_to_thread()` completes, it could `git add + commit` the thread files. This is the cleanest place because it works for both sync and async flows.

My recommendation: auto-commit in the worker process after all responses are written, with a config flag `council.auto_commit: true` (default true). The commit message should be `"council: <truncated prompt>"`. Don't prompt — that's incompatible with async mode. If the user doesn't want it, they set `auto_commit: false`.

**But beware**: this means the worker subprocess needs to run git commands. Currently it's a pure Python process that doesn't touch git. You'd be adding a new responsibility. Also, if the user has uncommitted changes staged, an auto-commit could capture unrelated work. Safest approach: `git add` only the specific thread directory, not `.`.

### 3. Phase 2 Feasibility and Hidden Complexity

**Textual as a dependency (your question #8).** Textual is the right call, but there are gotchas:

- **Textual is async-native (asyncio)**, but your council execution is thread-based (`ThreadPoolExecutor` in `council.py:63`). You'll need to bridge these: `asyncio.to_thread()` to run blocking agent queries from the Textual event loop, or refactor council execution to be async. The bridge is straightforward but must be designed explicitly.
- **Textual apps consume the terminal.** You can't run a Textual app and also use the same terminal for anything else. This is fine (separate pane), but it means `kd chat` must be a fully standalone process. No sharing stdin/stdout with other kd commands.
- **Rich markup in Textual.** Textual uses Rich internally, so your existing `render_response()` Rich Markdown rendering should mostly transfer. But Textual's `RichLog` widget has quirks with very long markdown — test with real council responses (which can be 2000+ words).
- **Input handling.** Textual's `Input` widget is basic. For a chat interface you'd want multi-line input (Shift+Enter for newline, Enter to send). Textual's `TextArea` widget can do this but needs custom key bindings.
- **The dependency itself.** Textual is ~50 files, pure Python, no C extensions. It's maintained by Will McGuinness (Textualize). It's a reasonable dependency for a CLI tool. Add it as an optional dependency group (`uv add --optional tui textual`) so users who only want `kd council ask` don't pull it in.

**Streaming from `.stream-{member}.md` files — the Codex problem (your question #6).** This is the trickiest part of Phase 2 and the design underspecifies it.

Currently, `CouncilMember.query()` at `base.py:87-92` tees raw stdout line-by-line to stream files. For Claude Code, stdout is a JSON blob that arrives after completion (`--print --output-format json`), so the stream file gets the raw JSON — not useful for progressive display. For Codex, stdout is JSONL events streamed incrementally — each line is a JSON object with `type` fields.

What you actually need for streaming display is **normalized incremental text**. This requires a per-backend "stream normalizer" that sits between raw stdout and the stream file:

- **Claude Code**: `--print` mode doesn't stream text progressively — it buffers the full response and outputs JSON at the end. To get true streaming, you'd need `--output-format stream-json` (if it exists) or parse Claude Code's stderr progress output. Otherwise, the Claude panel in the TUI will show nothing until the response is complete, then show everything at once. This partially defeats the purpose.
- **Codex**: JSONL events can be parsed incrementally. Extract `item.completed` → `item.text` as they arrive and write normalized text to the stream file.
- **Cursor**: Similar to Claude Code — likely buffered.

The design says "Reuse the existing `parse_codex_response()` logic" but that function (`agent.py:120`) operates on the *complete* stdout. For streaming, you need an *incremental* parser that handles partial JSONL. This is a new component.

**Where should normalization live?** I'd put it in `base.py`'s `read_stdout` closure (lines 87-92). Instead of blindly writing raw lines to the stream file, pass each line through a backend-specific normalizer that extracts displayable text. The stream file then contains plain prose, and the TUI can tail it without knowing anything about backends.

**Concurrent writes in auto-mode (your question #7).** The thread system's `add_message()` at `thread.py:249-292` uses exclusive file create (`open(..., 'x')`) with retry on `FileExistsError`. This handles concurrent writes correctly — two agents finishing simultaneously will get different sequence numbers. The retry loop (up to 10) is sufficient for 3 concurrent writers.

However, in auto-mode Phase 3, there's a subtler issue: **turn ordering**. If claude and codex both respond to round N simultaneously, their messages interleave unpredictably (whoever finishes first gets the lower sequence number). In round-robin mode, you probably want messages to appear in a fixed order (claude, then codex, then cursor). This means auto-mode should be *sequential* within a round, not parallel — which contradicts Phase 2's "broadcast" behavior (parallel first round).

The design should explicitly state: Phase 2 broadcast = parallel (first round only), Phase 3 auto-turns = sequential round-robin. The `mode` config field kind of addresses this ("broadcast" vs "sequential") but the semantics of "broadcast" are ambiguous — does it mean "first round parallel, then sequential" or "all rounds parallel"?

### 4. Phase 3 Risks and Missing Details

**"User typing interrupts auto-mode immediately" — what does "immediately" mean?** If codex is mid-generation (30 seconds into a 2-minute response), does the user's message:
1. Kill the in-progress generation? (Destructive — you lose partial work)
2. Queue after the current generation finishes? (Not "immediate")
3. Send immediately to all members while the current generation continues? (Chaotic — members see different thread states)

Option 2 is the only sane choice. "Immediately" should mean "auto-mode stops scheduling new turns, and the user's message is sent after the current turn completes." The design should be explicit about this.

**Session continuity across auto-turns.** Each auto-turn needs full thread context. Currently, council members get context via `--resume SESSION` which resumes the agent's conversation. But the agent's conversation only includes messages *it* sent and received through its own CLI — it doesn't include messages from other agents that were written to thread files.

For group chat to work, each auto-turn must inject the full thread history into the prompt, not rely on session resume. Otherwise claude won't see what codex said. This is a fundamental change to how `CouncilMember.build_command()` works. Currently it takes a single `prompt` string (line 49). For auto-turns, it needs to take the full thread history formatted as a multi-party conversation.

This is probably the single biggest hidden complexity in the design. Look at `build_command()` at `base.py:49-65` — the prompt is just a string. For group chat, you need something like:

```
[Previous thread messages formatted as conversation]
---
It's your turn. Respond to the discussion above.
```

And this needs to happen on every auto-turn, growing the context with each round. This isn't called out in the design at all.

**Stop condition: "all members produce short/empty responses."** What's "short"? Under 50 characters? Under 100? This needs a threshold or it'll be bikeshedded during implementation. I'd say: under 100 characters for all members in the same round = stop. Or just drop this condition entirely and rely on the hard cap. Keep it simple.

### 5. Config Design (your question #5)

The proposed `council.chat` shape:

```json
{
  "council": {
    "chat": {
      "auto_rounds": 3,
      "mode": "broadcast"
    }
  }
}
```

Missing fields I'd consider:
- `auto_commit`: `bool` (default true) — for ticket 1e3d
- `poll_interval_ms`: `int` (default 250) — how often the TUI polls stream files
- `stream_dir`: probably not needed, derivable from thread_dir

Fields to **not** add:
- `colors`: over-engineering, hard-code sensible defaults per member
- `max_message_length`: agents will produce what they produce
- `delay_between_turns`: SillyTavern uses this but it's only for RP pacing, not relevant here

The validation system in `config.py` is strict — `VALID_COUNCIL_KEYS = {"members", "timeout"}` at line 98. Adding `"chat"` means updating this set and adding a nested `ChatConfig` dataclass + validator. Straightforward but needs to be done carefully to maintain the existing validation error quality.

One concern: if `chat` is nested under `council`, the `VALID_COUNCIL_KEYS` check will reject it until you update the set. Good — the validation catches mistakes. But also consider: is `council.chat` the right nesting? `kd chat` is a top-level command. Maybe `chat` should be top-level in config too:

```json
{
  "council": { "members": [...], "timeout": 600 },
  "chat": { "auto_rounds": 3, "mode": "broadcast" }
}
```

This is more consistent with `kd chat` being a top-level command (not `kd council chat`). The chat feature uses council members but isn't a council sub-feature.

### 6. Dependency Ordering

The phases are mostly ordered correctly, but there are cross-cutting concerns:

**Stream normalization spans Phase 1 and Phase 2.** If you fix the streaming architecture in Phase 2, you'll want it available for `kd council watch` improvements in Phase 1 too. Consider: do the stream normalization work as part of Phase 1's "progress/status visibility" requirement (6412), then Phase 2 simply consumes normalized stream files.

**The `kd chat` command registration depends on whether Textual is installed.** If Textual is an optional dependency, you need a conditional import guard:

```python
try:
    import textual
    # register kd chat command
except ImportError:
    # register a stub that says "pip install kingdom[tui]"
```

This is a pattern decision that should be explicit in the design.

**Session reset per-member (Phase 1) is required before Phase 3 auto-mode.** If one member errors during auto-mode, you need to reset just that member and continue. The current `reset_sessions()` at `council.py:137-140` nukes everything. The Phase 1 per-member reset work directly enables Phase 3 error recovery.

### 7. Things That Will Bite You During Implementation

1. **Claude Code doesn't stream in `--print` mode.** This is the biggest gap. Your primary councillor will show a blank panel for 2-4 minutes, then dump everything at once. The TUI's streaming panels will feel alive for codex but dead for claude. You might need to investigate Claude Code's `--output-format stream-json` or accept this limitation and document it.

2. **Thread history injection for group chat.** As discussed above, session resume doesn't carry cross-agent context. You need a prompt builder that formats the full thread as a multi-party conversation. This is new code that doesn't exist today.

3. **Textual + subprocess orchestration.** Textual's event loop is asyncio. Your agent queries are blocking subprocesses with threading. The bridge (`run_in_executor` or `asyncio.to_thread`) works but error handling across the boundary is tricky — a subprocess timeout in a thread needs to surface as a Textual event that updates the UI.

4. **The `.stream-{member}.md` files are deleted after message completion** (`council.py:129-130`, `worker.py:58-59`). If the TUI is polling these files and they disappear mid-read, you'll get `FileNotFoundError`. The TUI needs to handle this race gracefully (file disappearing = message is finalized, switch to reading the thread message file).

5. **The `--async` worker is fire-and-forget.** `subprocess.Popen` at `cli.py:483-489` with all stdio to DEVNULL. If the worker crashes, nothing notices. Phase 1's error handling needs to add a mechanism for the watch command to detect worker death — either by checking the worker PID or by using a sentinel file.

### 8. Recommendations Summary

1. **Resolve the mute/unmute contradiction.** Use `@mute`/`@unmute` as runtime session state in the TUI, not slash commands or config.
2. **Close or move tickets 41fb and 520a.** They're either done or explicitly non-goals.
3. **Specify retry semantics for 6412.** When, how many times, with or without session reset.
4. **Specify what "richer status" actually reads** — PID checks, log parsing, or stream file presence.
5. **Address Claude Code's non-streaming `--print` mode.** Either investigate streaming output modes or set expectations that claude's panel won't stream.
6. **Add thread history injection to the design.** This is required for Phase 3 and is the biggest missing piece.
7. **Define auto-commit as worker-side, thread-dir-scoped `git add + commit`.** Config flag to disable.
8. **Move stream normalization to Phase 1** so both `kd council watch` and `kd chat` benefit.
9. **Make Textual an optional dependency group.** `kd chat` gracefully errors if not installed.
10. **Clarify "broadcast" mode semantics.** First round parallel then sequential, or all rounds parallel? Be explicit.

The overall design is sound. The thread system as single source of truth is the right call and the biggest thing that makes this attempt different from the previous failed TUI. The main risk is that the streaming experience for Claude Code specifically will disappoint — and since Claude is your primary councillor, that matters a lot. I'd investigate Claude Code's streaming output options before committing to Phase 2.
