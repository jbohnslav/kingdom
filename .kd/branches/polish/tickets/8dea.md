---
id: "8dea"
status: closed
deps: []
links: []
created: 2026-02-16T18:36:22Z
type: task
priority: 2
---
# kd chat Textual polish pass: research best-in-class apps and prioritize UX improvements

Run a focused `kd chat` UX polish pass based on Textual ecosystem research, then convert findings into prioritized implementation tickets.

Goals:
- Study high-quality Textual apps and official examples for interaction/layout patterns we should adopt.
- Review Textual testing + UX best practices (input ergonomics, scrolling behavior, status/help affordances, accessibility, copy/paste ergonomics, loading/streaming feedback).
- Examine existing Textual-based chat-style UIs (or closest analogs) and identify proven patterns we can reuse.

Research scope:
- Official Textual docs/examples and reference apps.
- Mature open-source Textual applications with strong UX polish.
- Existing issues in our backlog that overlap chat UX (copy/paste, markdown rendering, etc.).

Deliverables:
1. A short design/audit note (for example under `docs/`) with:
   - concrete examples reviewed
   - what each does well/poorly
   - applicability to `kd chat`
2. A prioritized improvement list for `kd chat`:
   - quick wins (low effort, high impact)
   - medium effort improvements
   - deferred/nice-to-have
3. Follow-up backlog tickets for each actionable improvement (small, testable, and scoped).

Acceptance criteria:
- Research note exists and references specific apps/patterns.
- At least 5 concrete `kd chat` polish opportunities identified.
- At least 3 follow-up tickets created with clear acceptance criteria.
- Overlap with existing tickets is reconciled (link or dedupe rather than duplicate).

## Worklog

### Research completed 2026-02-16

**Codebase reviewed:** All 5 TUI source files (`app.py`, `widgets.py`, `poll.py`, `clipboard.py`, `__init__.py`), all 3 test files (150+ test cases), and the CLI entry point.

**Reference apps studied:**
- Elia (darrenburns/elia) -- Textual LLM chat client
- Toad (batrachianai/toad) -- Universal AI terminal frontend by Will McGugan
- Textual official docs: Markdown widget, LoadingIndicator, get_stream(), external .tcss patterns

**10 concrete improvements identified** (see docs/chat-tui-polish-audit.md):
1. Replace WaitingPanel with LoadingIndicator (quick win)
2. Add /copy slash command (quick win)
3. Render streaming content as Markdown (quick win)
4. Switch MessagePanel to native Markdown widget (medium)
5. Extract CSS to external .tcss file (medium)
6. Add message timestamps (medium)
7. Improve king message styling (medium)
8. Click-to-copy on message panels (deferred)
9. Contextual footer keybindings (deferred)
10. Theme support (deferred)

**7 follow-up tickets created:**
- aad9: Replace WaitingPanel with LoadingIndicator
- c40b: Add /copy slash command
- ac46: Render streaming content as Markdown
- f517: Switch MessagePanel to native Markdown widget
- 774d: Extract CSS to external .tcss stylesheet
- b6ca: Add timestamps to message panels
- 55fd: Improve king message styling

**Overlap reconciled:** Reviewed existing tickets 3e60, 27ce, 7afc, 7a1d, cca0, 5e30. No duplicates -- new tickets address visual/UX polish not covered by existing functional tickets.
