---
from: codex
to: king
timestamp: 2026-02-17T01:17:31Z
---

Strong direction. I’d treat this as one polish initiative with many small, independently shippable tickets (mostly 0.5-1 day each), not mega tickets.

**Ticket Backlog (Polish-Only)**

**`tk` / ticket UX**
- `kd tk log` basic command: show chronological ticket events.
- `kd tk log --since/--until` time filters.
- `kd tk log --actor` filter by user/agent.
- `kd tk log --type` filter by event type.
- `kd tk log --follow` live tail mode.
- Add recent log preview to `kd tk show`.
- Human + absolute timestamps in log output.
- Redact sensitive values from logs.
- Golden tests for `kd tk log` rendering.

**Chat app message actions**
- Add `Reply` button on every assistant/user message.
- Add `Copy` button (plain text).
- Add `Copy Markdown` option.
- Show copied/replied success toast.
- Keyboard shortcuts: `r` for reply, `c` for copy.
- Preserve scroll position after reply insert.
- Include quoted context block in reply draft.
- Action buttons visible on hover + keyboard focus.
- E2E tests for reply/copy flows.

**Mentions polish**
- `@` mention autocomplete in composer.
- Tab-complete first match.
- Shift+Tab cycle backwards.
- Fuzzy match mention candidates.
- Accept mention with Enter as well as Tab.
- Highlight/colour mentions in composer.
- Highlight/colour mentions in rendered chat.
- Distinct style for unknown/invalid mentions.
- Mention autocomplete ranking by recency.
- E2E tests for mention insertion + rendering.

**Default colors / brand identity**
- Set default palette from brand ID (out of box).
- Truecolor detection with graceful fallback.
- Improve contrast for low-vision/readability.
- Colorblind-safe fallback palette option.
- `NO_COLOR` and `TERM=dumb` handling.
- Ensure status colors are semantically consistent.
- Snapshot tests for colored CLI output.

**Council permissions (interactive work)**
- Define explicit capability matrix (King / Council / Peasant).
- Allow council members to act on active ticket interactively.
- Allow council members to run approved commands in branch sandbox.
- Add deny-by-default for destructive operations.
- Per-action confirmation for high-risk operations.
- Log all council privileged actions to ticket events.
- Clear “permission denied” errors with next-step hint.
- Show capability badges in chat/council UI.
- Permission boundary tests (positive + negative cases).

**CLI output polish**
- Standardize success/warn/error wording across commands.
- Add “next step” hints on success outputs.
- Improve long-line wrapping in terminal output.
- Consistent table alignment + truncation rules.
- Better empty-state messages (no data, no tickets, etc.).
- More specific non-zero exit messages.
- Progress indicator for long council operations.
- Cleaner Ctrl+C interruption messaging.

**Error and recovery UX**
- Retry messaging for transient network failures.
- Preserve partial output when operation fails late.
- Timeout messages include concrete retry suggestion.
- Detect stale context and suggest refresh command.
- Better parsing errors for malformed flags/options.
- Improve unknown command typo suggestions.

**Onboarding and help polish**
- Tighten `kd help` examples to most common flows.
- Add short examples to high-friction commands.
- Add first-run hints that can be disabled.
- Document mention syntax and behaviour.
- Document color defaults and overrides.

**Accessibility + keyboard**
- Full keyboard navigation in chat action UI.
- Strong visible focus states.
- Better hit targets for message action buttons.
- Reduce-motion option for chat transitions.
- Screen-reader labels for reply/copy actions.

**Performance and responsiveness**
- Reduce perceived latency in chat send/render.
- Debounce mention search without lag.
- Avoid layout shift when message actions appear.
- Cache recent mention candidates for fast open.
- Track and improve slow-path council response UX.

**Dogfooding and polish process**
- Add `polish` backlog label and triage rule.
- Ticket template for polish tasks (small, measurable AC).
- Weekly polish sweep ticket.
- “UX papercut” intake ticket from dogfooding notes.
- Require manual spot-check after CLI output changes.

If you want, I can convert this into a prioritized top-20 cut (P0/P1) so the branch starts with maximum UX impact and minimal risk.
