---
id: "8dea"
status: open
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
