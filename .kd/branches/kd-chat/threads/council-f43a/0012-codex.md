---
from: codex
to: king
timestamp: 2026-02-16T11:43:04Z
---

Using the `kingdom` skill here because this is a ticket-scope design decision. I’ll quickly inspect `213e` plus existing thread/message code so the recommendations align with current architecture and constraints.
I found there is no `src/kingdom/tui/thread.py`; thread logic currently lives in `src/kingdom/thread.py`. I’ll inspect that module next to recommend placement and body-parsing behavior precisely.
I’ve got the relevant design section and thread APIs loaded. I’m now checking parsing behavior and current message-writing patterns to answer the markdown-header and directed-message policy questions concretely.
I confirmed the current code now persists member responses in `run_query`. I’ll do one more read of `AgentResponse.thread_body()` and similar paths to recommend exactly what “message bodies only” should mean for header stripping.
I have enough context; I’m drafting recommendations now with explicit decisions for module placement, body handling, directed-message visibility, and prompt format hardening.
Good ticket to implement next. I’d lock these decisions before coding:

1. Placement
Put `format_thread_history()` in a new council-layer module (for example `src/kingdom/council/history.py`), not `src/kingdom/thread.py`.
Reason: `src/kingdom/thread.py:429` is storage/read-model territory (`list_messages()`), while this function is prompt-construction policy for auto-turn behavior.

2. “Message bodies only” and markdown headers
Do not heuristically strip model-authored markdown like `## Response`.
Interpret AC as: strip transport metadata (frontmatter/preamble/injected instructions), keep authored body verbatim. `parse_frontmatter()` already removes frontmatter (`src/kingdom/parsing.py:88`), and persisted agent text is already `thread_body()` (`src/kingdom/council/base.py:26`).

3. Directed messages (`to != all`)
Include them in everyone’s injected history by default.
Reason: design says full shared thread context; filtering creates hidden-state divergence.
But include recipient metadata in the formatted transcript (for example `king -> claude:`), otherwise agents lose important routing context.

4. Output format quality
Current shape is understandable, but brittle for multiline bodies and `---` collisions.
I’d harden it with explicit boundaries and recipient labeling, plus a clearer tail instruction:
- start marker + end marker (not only `---`)
- include `from` and `to` per message
- final line: “You are {target_member}. Reply only as {target_member}. Continue from the latest message.”

Key extra decisions still missing:
1. Should synthetic error/timeout messages be included in history or skipped?
2. Empty thread behavior: exact output when no messages exist.
3. Validation: what happens if `target_member` is not in thread members.
4. Determinism rules: newline normalization and ordering by sequence only.
