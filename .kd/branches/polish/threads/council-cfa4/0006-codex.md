---
from: codex
to: king
timestamp: 2026-02-17T01:24:26Z
---

I’m going to pull the current ticket list with `kd tk list` first, then I’ll propose only net-new polish tickets that don’t overlap what’s already in scope. I’ll cross-check against both Claude’s and Cursor’s suggestions as I build the list.
I’ve got the current pulled ticket set. I’m doing one quick pass on `kd tk list --help` so I can verify whether we should also exclude already-existing backlog items before I propose the net-new list.
I confirmed open tickets across branch+backlog. I’ll do one final duplicate check against closed tickets for likely keywords (`reply`, `mentions`, `colors`, permissions, etc.) so the “new” list is truly net-new.
Checked with `kd tk list --all --include-closed`; below are **net-new** polish tickets (not currently present).

**`tk` and ticket UX**
- `kd tk log: add --since/--until time filters`
- `kd tk log: add --actor filter`
- `kd tk log: add --type filter`
- `kd tk log: add --follow live tail mode`
- `kd tk log: render absolute + relative timestamps`
- `kd tk log: redact secrets/tokens from logged payloads`
- `kd tk show: add recent activity preview from ticket log`
- `kd tk log: add golden/snapshot rendering tests`

**Chat message actions and composer**
- `kd chat: add Reply action on each message`
- `kd chat: Reply inserts quoted context + @author in draft`
- `kd chat: add Copy Markdown action (separate from plain copy)`
- `kd chat: show success toast/status for copy/reply actions`
- `kd chat: keyboard shortcuts for focused message actions (r/c)`
- `kd chat: preserve scroll position when creating a reply draft`
- `kd chat: keep message action buttons keyboard-focusable (not hover-only)`
- `kd chat: slash-command discoverability in composer (hint/autocomplete)`
- `kd chat: add hotkey to toggle thinking visibility globally`
- `kd chat: improve smart autoscroll to avoid snap-to-bottom while reading history`
- `kd chat: format long thinking durations as mm:ss`
- `kd chat: show actionable retry hint in error panel`
- `kd chat: avoid member-color collisions when >6 members`

**Mentions polish**
- `kd chat mentions: Shift+Tab cycles backward through suggestions`
- `kd chat mentions: Enter accepts selected suggestion`
- `kd chat mentions: fuzzy matching for member names`
- `kd chat mentions: rank suggestions by recent usage`
- `kd chat mentions: syntax highlight in composer as you type`
- `kd chat mentions: distinct style for unknown/invalid @mentions`
- `kd chat mentions: keyboard-only E2E tests for insertion flow`
- `kd chat mentions: preserve mention styling in wrapped/truncated rendered lines`

**Color and terminal behavior**
- `kd chat/cli: respect NO_COLOR and TERM=dumb consistently`
- `kd chat/cli: detect truecolor support and degrade gracefully`
- `kd chat: optional colorblind-safe palette mode`
- `kd chat: enforce minimum contrast for branded member colors`
- `kd cli/tui: standardize semantic status colors (success/warn/error/info)`
- `kd chat/cli: snapshot tests for color output across terminal capabilities`

**Council permissions decomposition**
- `kd council: define explicit capability matrix (King/Council/Peasant)`
- `kd council writable mode: allowlist safe tool actions`
- `kd council writable mode: confirmation gate for high-risk actions`
- `kd council permissions: clear denial messages with next-step hints`
- `kd council permissions: log privileged actions to ticket events/worklog`
- `kd chat: show capability badges for each council member`
- `kd council writable mode: add permission boundary tests (allow/deny)`
- `kd council writable mode: timeout/cancel handling for interactive tool calls`
- `kd council: add audit view for privileged actions in a thread`

**CLI polish and recovery**
- `kd cli: standardize success/warn/error message templates`
- `kd cli: add “next step” hints on successful commands`
- `kd cli: improve empty-state messages with actionable commands`
- `kd cli: consistent table wrapping/truncation rules`
- `kd cli: improve unknown-command typo suggestions`
- `kd council/chat: preserve partial output on late-stream failures`
- `kd council/chat: retry guidance for transient provider/network errors`
- `kd council/chat: timeout messages with concrete retry flags`
- `kd cli: cleaner Ctrl+C interruption messaging`
- `kd council show: add --last N (or paging) for long threads`
- `kd council status: add symbol legend output`

If you want, I can do a second pass that trims this to a **P1 create-now cut (top 15)**.
