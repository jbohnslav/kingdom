---
from: claude
to: king
timestamp: 2026-02-17T12:51:07Z
---



Let me search through the docs and archive for additional "why" points.That's a thorough haul. Here are the "why" arguments from the docs that aren't already covered by our five bullets:

1. **Independence by default** — Council members don't see each other's answers unless you put them in debate mode. Avoids groupthink and anchoring — you get genuinely diverse perspectives, not one model's bad idea polluting the rest. (from `docs/blogs/claude-code-teams.md`, `docs/council-as-supervisor.md`)

2. **Session continuity** — Follow-up questions to council members reuse their session context. No re-sending the entire conversation. Cheaper, faster, and the model refines its thinking across turns. (from `docs/council-design.md`)

3. **Worklog as audit trail** — Peasants append decisions, bugs encountered, and test results to a worklog section in each ticket. It's committed to git, so you can always see *why* a choice was made, not just what changed. (from `docs/multi-agent-design-v3.md`)

4. **Atomic task claiming** — Multiple peasants can run in parallel without race conditions. Task claiming is atomic, so two workers never pick the same ticket. (from `docs/blogs/claude-code-teams.md`)

5. **No server, no database, headless-friendly** — Everything is files on disk. Works over SSH, in CI, in containers. No infrastructure to maintain. (from `docs/architecture.md`, `docs/multi-agent-design-v3.md`)

6. **Not vendor-locked** — Agent backends are config entries, not hard-coded. Swap Claude for Codex for Gemini. Use expensive models for design, cheap ones for execution. (from `docs/council-design.md`, `docs/architecture.md`)

7. **Quality gates before merge** — `kd peasant review` runs tests, lints, and shows the diff + worklog. Accept or reject — peasant can retry if rejected. (from `docs/multi-agent-design-v3.md`)

Some of these reinforce existing bullets (like #4 and #5 expanding on "markdown files" and "parallel execution"), and some are genuinely new angles (#1 independence/groupthink, #2 session continuity, #3 worklog audit trail). The independence point is probably the strongest one missing — it's a real differentiator against tools where agents collaborate and converge on a single answer.

@codex — which of these do you think are worth adding as bullets vs. already implied by what we have?
