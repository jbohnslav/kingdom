---
id: "efaf"
status: closed
deps: []
links: []
created: 2026-02-16T18:58:53Z
type: task
priority: 1
---
# kd chat: add copy-to-clipboard action for each council message

Add a per-message copy action in `kd chat` so users can quickly copy any council response without manual text selection.

Context:
- Mouse selection/copy in terminal TUIs can be unreliable.
- A first-class copy action would improve usability for sharing or reusing model output.

Scope:
- Add a visible copy affordance for each council message in the chat TUI (button/action per message panel).
- Copy the message body (and optionally sender+timestamp formatting, if specified) to clipboard.
- Provide clear success/failure feedback in the UI.
- Handle environments where clipboard access is unavailable (graceful fallback message).

Acceptance criteria:
- Every council message has an accessible copy action in the TUI.
- Triggering copy places the expected message content on clipboard in supported terminals/environments.
- If clipboard is unavailable, user gets a clear non-crashing error/help message.
- Add automated tests for copy action behavior (including unavailable clipboard path).

Notes:
- Related UX ticket: `ecf7` (mouse reporting makes copy/paste hard).

## Worklog

### 2026-02-16 — Implementation complete

**Approach:** Click-to-copy on `MessagePanel` using system clipboard commands via subprocess. No third-party dependencies.

**Files added:**
- `src/kingdom/tui/clipboard.py` — Cross-platform clipboard utility (pbcopy on macOS, xclip/xsel on Linux). Raises `ClipboardUnavailableError` when no command is found.
- `tests/test_tui_clipboard.py` — 16 tests covering clipboard detection, copy success/failure, MessagePanel click behavior, and graceful degradation.

**Files modified:**
- `src/kingdom/tui/widgets.py` — `MessagePanel` now shows "click to copy" border subtitle on council messages, copies body on click with 2-second feedback ("copied!" / "clipboard unavailable" / "copy failed").
- `src/kingdom/tui/app.py` — Help text updated to mention click-to-copy.

**Design decisions:**
- King messages are excluded from copy (no border, no affordance — they're your own input).
- Uses `border_subtitle` for the hint and feedback — subtle, non-intrusive, visible.
- Feedback resets after 2 seconds via `set_timer`.
- Standard library only (subprocess + shutil.which) — no pyperclip dependency.
