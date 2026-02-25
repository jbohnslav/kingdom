# Design: groupchat

## Goal
Make group chat feel like a real multi-agent conversation with distinct orchestration modes — from fully automatic discussion to fully manual control — with clean config separation between chat and council query paths.

## Context
`kd chat` already supports broadcast (parallel) and sequential modes, auto-turns with a message budget, @mention parsing for king messages, generation-based interrupt detection, and thread history injection. But the orchestration is wired to council-era config (`council.mode`, `council.auto_messages`) rather than chat-specific fields. The current auto-turn loop iterates members in fixed order every time, which means the first member always anchors the discussion.

### What works today
- **Broadcast**: king sends → all active members respond in parallel (first exchange skips auto-turns)
- **Sequential auto-turns**: after broadcast, iterate `member_names` in fixed order, counting messages against `auto_messages` budget
- **@mentions**: king can direct messages with `@claude`, `@codex`, `@all`; unknown names fall back to broadcast
- **Interrupts**: `self.generation` increments on king send; running auto-turns check and bail
- **Muting**: `/mute <name>` excludes member from targets and auto-turns

### What's broken or missing
- `chat_mode` and `chat_auto_rounds` config fields are validated but never read by ChatApp
- Auto-turns use a flat message count (`auto_messages`), not rounds
- Member ordering is fixed — claude always goes first, anchoring every round
- LLM responses can't @mention each other to redirect the conversation
- `kd chat <thread-id>` can resolve/open the wrong thread in practice (6b22)
- `WaitingPanel` DuplicateIds crash from async removal race (05e1)
- CLI error messages print twice (7c4a)

## Requirements

### Chat modes (7afc)

Four distinct modes, each with its own first-turn and auto-turn behavior:

| Mode | First turn | Auto-turns | `auto_rounds` meaning |
|---|---|---|---|
| **`natural`** (default) | parallel broadcast | shuffled round-robin | rounds of round-robin after broadcast |
| **`round_robin`** | first member in order | fixed-order sequential | rounds of sequential turns |
| **`manual`** | only @mentioned members | only @mentioned members | ignored |
| **`broadcast`** | parallel to all | parallel to all | number of auto-broadcast rounds |

- **`natural`**: king asks → all members respond in parallel → then shuffled round-robin for `auto_rounds` rounds. Each round randomizes who speaks first, preventing any single agent from anchoring the discussion. This is the default for getting independent opinions followed by organic discussion.
- **`round_robin`**: no initial broadcast. First member in config order speaks, then the rest in order, cycling for `auto_rounds` rounds. For structured turn-taking where build-on-each-other matters more than independent takes.
- **`manual`**: every response must be explicitly targeted via @mention, including the first turn. No auto-turns, no broadcast. King has full control. If the king sends a message without @mentioning anyone, show a hint: "Manual mode — @mention a member to get a response."
- **`broadcast`**: every turn fans out to all active members in parallel. No sequential discussion. `auto_rounds` controls how many additional parallel rounds happen after the king's initial broadcast. For getting N independent answers every time.

### Round-robin orchestration (27ce)
- A **round** = one full pass through all eligible (non-muted) members
- In `natural` mode: `random.shuffle(active)` at the start of each round
- In `round_robin` mode: iterate config order (minus muted)
- Stop after `auto_rounds` rounds (hard cap, no heuristics)
- Default `auto_rounds`: 1

### Interrupts (27ce)
- King typing during auto-turns: stop scheduling new turns, let current generation complete, then process king's message
- This already works via generation checking — just needs to be preserved as we refactor

### LLM-to-LLM @mentions (7a1d)
- After each auto-turn response, scan the member's output for `@member` patterns (same regex as king: `(?<!\w)@(\w+)`)
- If mentions are found and valid: apply **mention bump** — build the round order from the mode first (shuffle for `natural`, fixed for `round_robin`), *then* move mentioned members to front while others keep their relative order
- Example: shuffled order is `[codex, claude, gemini]`, last speaker @mentioned claude → round becomes `[claude, codex, gemini]`
- Unknown names and `@king` are ignored (no special behavior)
- Mention bump applies only in `natural` and `round_robin` modes (not `manual` or `broadcast`)
- Mention-bumped members still count toward the round's member list (no extra turns)

### Bug fixes
- **6b22 (thread-id routing)**: explicit thread selection must be deterministic and never silently fall back.
  - `kd chat <thread-id>` resolves that thread first (exact/prefix), or exits with a clear error.
  - Explicit ID takes precedence over both `current_thread` and "most recent" fallback behavior.
  - If explicit thread resolves, launch TUI on that thread and set it as `current_thread`.
  - Add CLI tests for exact match, prefix match, ambiguous prefix, and not-found.
- **05e1 (DuplicateIds)**: `send_message()` calls sync `remove_member_panels()` then immediately mounts new `WaitingPanel`. The DOM removal is async and hasn't settled. Fix: await removal before mounting, or check for existing widget and skip/reuse.
- **7c4a (double errors)**: `print_error()` writes to stderr, then `raise typer.Exit(1)` causes Typer to also echo. Fix: use a consistent pattern — either raise `typer.Exit` without printing first, or print and `sys.exit(1)`.

### TUI improvements
- **f4f9 (Shift+Enter)**: Insert a newline in the chat input area on Shift+Enter instead of submitting.
- **190e (toggle reply)**: Click a chat message to set reply target, click again to undo.

### Config changes

Nested config separating the two execution paths. Old flat keys are removed with a fail-fast migration error.

**New structure:**
```yaml
council:
  ask:
    mode: broadcast        # for kd council ask
    auto_messages: -1      # for kd council ask (-1 = unlimited)
  chat:
    mode: natural          # natural | round_robin | manual | broadcast
    auto_rounds: 1         # rounds of auto-turns (ignored in manual)
```

**Migration:**
- Old keys (`council.mode`, `council.auto_messages`, `council.chat_mode`, `council.chat_auto_rounds`) → fail fast with a clear error telling the user to migrate to the nested format
- No backwards compatibility shims, no deprecation period

**Implementation:**
- `CouncilConfig` gets nested sub-dataclasses: `AskConfig` and `ChatConfig`
- `ChatApp` reads `council.chat.mode` and `council.chat.auto_rounds`
- `council.py` reads `council.ask.mode` and `council.ask.auto_messages`
- Valid chat modes: `"natural"`, `"round_robin"`, `"manual"`, `"broadcast"`

## Non-Goals
- Intelligent stop conditions (sentiment analysis, convergence detection) — hard cap only
- Agent-initiated new topics or unprompted messages
- Weighting or priority systems for agents beyond @mention bumping
- Changing council (non-chat) query behavior beyond config restructuring
- Streaming UI redesign
- `random` mode (pick one random member per turn) — defer to a follow-up ticket if needed

## Decisions
1. **"Round" = full pass through members**: not a single message. `auto_rounds: 2` with 2 active members = 4 auto-turn messages total.
2. **Shuffle per round, not per session**: in `natural` mode, each round gets a fresh `random.shuffle()`. Over multiple rounds, every agent gets to go first sometimes.
3. **Each mode has distinct first-turn behavior**: `natural` and `broadcast` start with parallel broadcast. `round_robin` starts with sequential first-in-order. `manual` requires explicit @mentions from turn one. No shared "always broadcast first" behavior.
4. **@mention bump applied after base order**: build round order from mode first, then move mentioned members to front while preserving relative order of others. This composes cleanly with both shuffle and fixed ordering.
5. **Fix bugs before features**: 6b22, 05e1, and 7c4a ship first; 6b22 is P1 correctness and 05e1 crash risk increases as orchestration complexity grows.
6. **Manual mode is strict**: no implicit broadcast, no fallbacks. If you don't @mention, you get a hint, not a response.
7. **No backwards compatibility**: old config keys fail fast with a migration error. Clean break.

## Ticket Ordering
1. **6b22** — thread-id argument ignored (P1, users can't resume specific chats)
2. **05e1** — DuplicateIds crash fix (unblocks safe auto-turn testing)
3. **7c4a** — double error messages (clean test output)
4. **f4f9** — Shift+Enter newline (small TUI fix, independent)
5. **27ce** — round-robin orchestration + config restructuring (core feature)
6. **7afc** — chat mode definitions: natural, round_robin, manual, broadcast (builds on 27ce)
7. **7a1d** — LLM-to-LLM @mentions with mention bump (layers on top of round-robin)
8. **190e** — toggle reply (independent TUI feature)
9. **c869** — docs update (last, after features stabilize)
