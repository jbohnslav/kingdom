# Design: usability-council-peasant

## Goal

Improve the daily experience of using `kd chat` and `kd peasant` — better rendering, better observability, tighter config validation, and housekeeping fixes surfaced by council review.

## Context

The chat TUI works but has rough edges: streaming content renders as plain text (not Markdown), inline CSS is scattered across widget classes, king messages are visually flat, and agents answer in isolation rather than engaging with each other. Peasants are a black box — you launch one and wait. Config validation is piecemeal (no startup check, no `council.chat` keys). A prior council review (58ba) surfaced 7 concrete bugs. The kingdom skill doc has grown unwieldy.

## Requirements

### R1 — Bug fixes from council review (58ba)
Fix all 7 issues: dead ternary in `cmd_copy`, dep-tree `--full` cycle crash, misleading "completed" peasant label, `tk closed` omitting done branches, self-links in `tk link`, dep-cycle including closed tickets, config docs preamble constraint.

### R2 — Chat TUI rendering
Implementation order: f517 → ac46 → 774d → 55fd (widget migration first, then streaming Markdown is just updating the new widget).

- **Native Markdown widget** (f517): Replace `Static` + `RichMarkdown` in `MessagePanel` with Textual's native `Markdown` widget. Note: this may affect `ColoredMentionMarkdown` @mention coloring — preserve or find equivalent.
- **Markdown streaming** (ac46): Render streaming content as Markdown, not plain text. With f517 done, this is updating a `Markdown` widget's content.
- **Extract CSS** (774d): Move all inline `DEFAULT_CSS` from widget classes and `ChatApp.CSS` into an external `.tcss` stylesheet. Do integration tests (R8) after this.
- **King message styling** (55fd): Give king messages visual distinction (subtle border or background) so they don't disappear into the conversation flow.

### R3 — Chat behavior
- **Engagement prompt** (a857): Update the council preamble (`base.py:65`) so agents engage with each other's responses. The chat preamble (`app.py:46`) already has this language — council doesn't. Keep it simple: update the text, manually verify, done.
- **Tool use / progress** (5574): Surface tool-use events and progress updates in the chat TUI during agent responses (e.g., "reading file X", "running command").

### R4 — Peasant observability
Split into three pieces:
- **R4a — Continuous work logs**: Peasants must append to their work log as they work, not just at completion. Make this a harder contract in the harness.
- **R4b — `kd peasant watch <id>`**: New command under the peasant subgroup. Shows real-time progress: work log appends, diffs, ticket updates. Tail-like CLI stream, not a TUI. Exits on Ctrl+C or when the peasant finishes (whichever comes first).
- **R4c — Tmux mode**: `kd peasant start --tmux <id>` opens the agent in a new tmux window. User can rearrange into panes themselves.

### R5 — Config validation (e880, e5dd)
- Add `chat_mode` and `chat_auto_rounds` as flat keys in the council config (alongside existing `mode`, `auto_messages`, etc.). Add to `VALID_COUNCIL_KEYS` and `CouncilConfig` dataclass. No nested `council.chat` section — keep the config flat. No migration or deprecation.
- Validate config on startup (`kd start`, `kd chat`, `kd council ask`) — surface errors early instead of crashing mid-operation.

### R6 — Thread message metadata (9124)
Add optional `status` field to thread message YAML frontmatter (values: `complete`, `error`, `timeout`, `interrupted`). No separate `error` boolean — status alone is sufficient.

### R7 — Verbose flag (d04c)
Add `--verbose` / `-v` global flag to the root `kd` app. When set, print debug output: resolved file paths, config source, log level. Implement early — useful as a dev aid while building everything else.

### R8 — Integration tests (cca0, b93f, 5e30)
Write after CSS extraction (774d) to avoid rewriting CSS loading twice.
- **StreamingPanel visibility** (cca0): Integration test that StreamingPanel appears during a query and is replaced by MessagePanel on completion.
- **FakeMember protocol** (b93f): Test that FakeMember satisfies the CouncilMember protocol, catching interface drift.
- **ThinkingPanel lifecycle** (5e30): Test auto-collapse on answer start, hide mode, show mode, persistence.

### R9 — Rewrite kingdom skill (6ad7)
Rewrite `skills/kingdom/SKILL.md` for brevity and readability. Consolidate the two skill files: `skills/kingdom/SKILL.md` (repo/dev copy) and `src/kingdom/skill/SKILL.md` (packaged copy) have drifted apart. Make the packaged copy a build artifact from the repo copy, or eliminate the duplication.

### R10 — ThinkingPanel crash fix (6a1e)
Fix `ValueError: Node 'id' attribute may not be changed once set` at `app.py:957`. ThinkingPanel id reassignment after mount is prohibited by current Textual. Stop reassigning the id.

## Non-Goals
- Group chat auto-mode / round-robin orchestration (27ce) — future branch.
- LLM-to-LLM @mentions (7a1d) — future branch.
- Auto-commit on council responses — removed from scope.
- New agent backends (Gemini CLI, OpenCode) — separate work.
- Config migration/deprecation — not needed, sole user.

## Decisions
- **Implementation order**: 58ba (7 bug fixes) → 6a1e (ThinkingPanel crash) → b1e1 (scroll fixes) → d04c (verbose flag) → R2 (f517 → ac46 → 774d → 55fd) → R3 (a857, 5574) → R4 (5b14) → R5 (e880, e5dd) → R6 (9124) → R7 (6ad7) → R8 (cca0, b93f, 5e30).
- **CSS extraction**: Single `.tcss` file at `src/kingdom/tui/chat.tcss`, loaded by `ChatApp`. Widget classes lose their `DEFAULT_CSS` blocks.
- **Markdown widget**: Use Textual's built-in `Markdown` widget. `MessagePanel` becomes a container that holds a `Markdown` child rather than being a `Static` that renders `RichMarkdown`. Preserve @mention coloring or find equivalent in the new widget.
- **Peasant watch**: `kd peasant watch <id>` — under the existing peasant subgroup, not a root command.
- **Tmux mode**: New tmux window (not pane). Requires tmux to be running; error if not.
- **Config**: No migration. Add `chat_mode` and `chat_auto_rounds` as flat keys to `council` config section.
- **Thread message status**: Optional `status` field in frontmatter. No separate `error` boolean.
- **Verbose flag**: Global `--verbose` callback on the root Typer app sets a module-level flag.
- **Skill consolidation**: Delete `src/kingdom/skill/` entirely. Ship `skills/kingdom/` as package data instead (update pyproject.toml). Change `install_skill()` to read from the same `skills/kingdom/` directory. One file, no copies — what the dev uses is what `kd init` installs.

## Resolved Questions
- **Tmux: window vs pane?** New window. User can rearrange via tmux.
- **Tool-use surfacing (5574):** Add `extract_stream_tool_use()` per-backend extractors in `agent.py` (same pattern as text/thinking extractors), a new `ToolUseEvent` in `poll.py`, and render it in the chat TUI. Real stream logs confirm the formats:
  - Claude Code: `stream_event` wrapping `content_block_start` with `type: "tool_use"` + input deltas
  - Cursor: `{"type": "tool_call", "subtype": "started", "tool_call": {"shellToolCall": {"args": {"command": "..."}}}}` and `subtype: "completed"` with results
  - Codex: `item.completed` events (need to capture tool-use item types — investigate during implementation)
- **Engagement prompt scope**: Council preamble only (`base.py:65`). Chat preamble already has engagement language.
- **58ba**: Keep as one ticket — Opus can crush all 7 in sequence.
