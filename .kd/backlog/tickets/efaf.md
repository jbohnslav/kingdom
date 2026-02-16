---
id: "efaf"
status: open
deps: []
links: []
created: 2026-02-16T18:58:53Z
type: task
priority: 2
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
