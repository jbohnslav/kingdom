# kd chat TUI Polish Audit

Research note for ticket 8dea. Reviewed the current `kd chat` implementation against best-in-class Textual applications and identified concrete improvements.

## Reference Apps Reviewed

### Elia (darrenburns/elia)
Terminal LLM chat client built with Textual. Key strengths:
- Uses Textual's native `Markdown` widget (not `Static` + `RichMarkdown`) for message rendering, gaining interactive features like scrollable code fences, clickable links, and proper table rendering.
- External `.tcss` stylesheets separated from Python code, enabling live-reload during development and cleaner code separation.
- Multiple built-in themes with YAML-based custom theme definitions.
- Keyboard-centric design with discoverable bindings (Ctrl+O for options).
- SQLite-backed conversation storage with archive/rename support.

### Toad (batrachianai/toad)
Universal AI terminal frontend by Will McGugan (Textual creator). Key strengths:
- Streaming Markdown rendering with syntax-highlighted code fences, tables, quotes, and lists — all rendered properly during streaming, not just after finalization.
- Prompt editor with full keyboard/mouse navigation, selection, cut/copy/paste, and live Markdown syntax highlighting.
- `@` file picker with fuzzy search for context injection.
- Notebook-style interaction: move through previous conversation blocks, reuse them, copy to clipboard.
- Side-by-side diff views.
- Contextual footer keybindings that change based on current state.
- Settings UI (not manual JSON editing).

### Textual Official Patterns
- `LoadingIndicator` widget: pulsating dots animation for long-running operations. Built-in, zero-effort replacement for our hand-rolled `WaitingPanel`.
- `Markdown` widget with `get_stream()` for background streaming updates — combines multiple rapid updates to maintain responsiveness.
- `Markdown` widget provides scrollable code blocks, clickable links, and table rendering vs. `Static`+`RichMarkdown` which renders all content inline.
- External `.tcss` files recommended for style separation and live-reload development.

## Current State Assessment

### What kd chat does well
1. **Streaming architecture is solid.** File-based polling with NDJSON stream parsing handles multi-backend (Claude/Codex/Cursor) differences correctly. Retry detection, cross-batch accumulation, and thinking token extraction all work.
2. **Multi-agent orchestration works.** Broadcast, sequential, directed messages, mute/unmute, auto-turn round-robin with budget control — all functional.
3. **Interrupt handling is correct.** Escape kills processes, replaces panels, persists partial text, labels interrupted responses.
4. **Thinking panel UX is good.** Auto-collapse on first answer token, manual pin toggle, elapsed time display.
5. **Test coverage is thorough.** 150+ unit tests and 12 integration test scenarios covering the full lifecycle.

### What needs improvement

#### 1. Message Rendering: Static+RichMarkdown instead of Markdown widget
**Current:** Messages use `Static` widget with `RichMarkdown` renderable.
**Problem:** No scrollable code fences, no clickable links, no proper table rendering. Content is rendered as a flat static block.
**Best practice:** Both Elia and Toad use the native `Markdown` widget, which provides interactive code blocks, proper tables, and link handling out of the box.

#### 2. No Copy-to-Clipboard on Messages
**Current:** `clipboard.py` exists but is never wired to any UI action. Users cannot copy a message to clipboard.
**Problem:** In a chat TUI where you need to act on agent suggestions, inability to copy is a significant friction point.
**Best practice:** Toad supports per-block clipboard copy. Elia supports text selection. At minimum, a click-to-copy or keybinding on message panels is needed.

#### 3. WaitingPanel is Plain Text
**Current:** `WaitingPanel` shows "member — waiting..." as border title on a 1-height dashed box.
**Problem:** No animation feedback. Users can't tell if the app is alive or hung during long waits (council queries can take minutes).
**Best practice:** Textual provides `LoadingIndicator` (pulsating dots) out of the box. Any loading state should have animation to signal liveness.

#### 4. All CSS is Inline
**Current:** Styles are defined via `DEFAULT_CSS` strings in Python classes and `CSS` classvar in the app.
**Problem:** Harder to iterate on visual design. No live-reload during development. Mixes presentation with logic.
**Best practice:** Textual recommends external `.tcss` files (set via `CSS_PATH`). Both Elia and Toad separate styles from code.

#### 5. StreamingPanel Uses Plain Text Instead of Markdown
**Current:** `StreamingPanel.update_content()` calls `self.update(text + cursor_char)` — raw text, not rendered Markdown.
**Problem:** While streaming, content looks like raw markup. Only finalized messages get Markdown rendering. This is jarring when a long response streams as raw text then suddenly re-renders as formatted Markdown.
**Best practice:** Toad renders Markdown during streaming. Textual's `Markdown.get_stream()` is designed for exactly this use case.

#### 6. No Keyboard Shortcut to Copy Last Response
**Current:** No keybinding exists for copying the most recent agent response.
**Problem:** Common workflow: ask question, get answer, copy answer. Currently requires manual terminal selection.
**Best practice:** Toad and Elia both provide clipboard integration for conversation content.

#### 7. Header Bar is Minimal
**Current:** Header shows `kd chat . thread-id . member1 member2` as plain text.
**Problem:** No visual distinction, no theme awareness. Doesn't show which members are muted or active query status.
**Best practice:** Textual provides `Header` and `Footer` widgets with built-in theme integration. At minimum, status-aware header content.

#### 8. No Timestamps on Messages
**Current:** Messages show sender name only. No timestamp or elapsed time.
**Problem:** In long conversations, temporal context is lost. Hard to tell when a response was given.
**Best practice:** Most chat apps show timestamps. At minimum, relative timestamps ("2m ago") would help.

#### 9. King Messages Have No Visual Distinction Beyond CSS
**Current:** King messages have `border: none` and muted color — they look like system text.
**Problem:** In a multi-agent chat, the king's messages should be visually prominent as the anchor of conversation flow.
**Best practice:** Right-aligned or indented king messages (like iMessage/WhatsApp visual convention) or a distinctive background/border style.

#### 10. No `/copy` Slash Command
**Current:** Slash commands: `/mute`, `/unmute`, `/help`, `/quit`.
**Problem:** Missing obvious utility commands like `/copy` (copy last response), `/clear` (clear screen), `/retry` (re-send last query).
**Best practice:** Chat interfaces typically provide rich slash-command sets.

## Prioritized Improvement List

### Quick Wins (Low Effort, High Impact)
1. **Replace WaitingPanel with LoadingIndicator** — Use Textual's built-in animated loader. ~30 min.
2. **Add `/copy` slash command** — Copy last agent response to clipboard. `clipboard.py` already exists. ~30 min.
3. **Render streaming content as Markdown** — Change `StreamingPanel` to use `Markdown` widget or `RichMarkdown` at minimum. ~1 hr.

### Medium Effort Improvements
4. **Switch MessagePanel to Textual Markdown widget** — Replace `Static`+`RichMarkdown` with native `Markdown`. Gains scrollable code blocks, clickable links, table rendering. ~2 hrs.
5. **Extract CSS to external .tcss file** — Move all `DEFAULT_CSS` and `CSS` definitions to `chat.tcss`. ~1 hr.
6. **Add message timestamps** — Show relative or absolute timestamps on message panels. ~1 hr.
7. **Improve king message styling** — Give king messages a right-aligned or visually distinctive treatment. ~1 hr.

### Deferred / Nice-to-Have
8. **Click-to-copy on message panels** — Add a click handler or keybinding on each panel to copy its content.
9. **Contextual footer keybindings** — Footer changes based on state (streaming vs. idle vs. interrupted).
10. **Theme support** — Allow configurable color themes beyond the hardcoded member colors.
11. **`/retry` slash command** — Re-send the last king message.
12. **`/clear` slash command** — Clear the message log display (not the thread history).

## Overlap with Existing Backlog

- **3e60** (Phase 2 chat TUI) — Already marked complete by current implementation. Some items above go beyond Phase 2 scope.
- **27ce** (Phase 3 auto-mode orchestration) — Auto-turns already implemented in current code. Ticket may need update.
- **7afc** (Group chat modes) — Covers natural/pooled/manual ordering. Separate from polish concerns.
- **7a1d** (LLM-to-LLM @mentions) — Complementary to polish; different scope.
- **cca0** (Integration test: streaming state) — Related to StreamingPanel improvements.
- **5e30** (Integration test: ThinkingPanel lifecycle) — Related to thinking panel polish.

## Follow-up Tickets Created

See backlog for tickets created from this audit.
