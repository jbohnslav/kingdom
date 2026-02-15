---
from: codex
to: king
timestamp: 2026-02-14T23:35:51Z
---

I’ll analyze this as a product/design review and keep it implementation-free. First I’m going to read the `kingdom` skill guidance, then `docs/third_party/llm-council.md`, then inspect current `kd` council UX surfaces to ground recommendations in what exists today.
I’m using the `kingdom` skill here because this is directly about council workflow UX in `kd`. Next I’m pulling current council docs/help (`skills/kingdom/references/council.md`, `docs/council-design.md`, `kd council --help`) plus the SillyTavern group chat doc for interaction patterns.
I have the current CLI surface confirmed (`ask`, `watch`, `status`, async/no-watch), and I’m now mapping the actual runtime flow in code so the recommendations line up with what would be cheap vs expensive to change. I’ll use an explorer agent for that codebase scan.
**Council CLI flow**

`kd council ask` in `src/kingdom/cli.py` is the entry point. It resolves the current feature, creates/continues a thread via `create_thread`/`set_current_thread`, writes the king’s prompt using `thread.add_message`, and then either (a) runs `Council.query_to_thread` for the blocking path, (b) delegates to the async worker, or (c) emits JSON if `--json`. The default (sync) path renders each response through `render_response` as they arrive, while the `--async` path prints the thread summary, spawns `python -m kingdom.council.worker` in a detached subprocess, and either exits (`--no-watch`) or falls through to `watch_thread` to stream responses as new message files appear. Status display relies on `thread_response_status` (from `thread.py`) and `council_watch` just reuses `watch_thread`, so much of the UX is driven by `Console`, `Markdown`, and `Progress` panels defined later in the same file. citenone

**Async orchestration and streaming**

`src/kingdom/council/council.py` contains the `Council` orchestration. `query_to_thread` launches each `CouncilMember.query` in a thread pool, passes a `.stream-{member}.md` path so `CouncilMember` tees stdout line-by-line (see `src/kingdom/council/base.py`), and writes final responses back to the thread via `add_message`. The `.stream-*` files live inside the thread directory, survive until the future completes, and are deleted afterward. The async worker (`src/kingdom/council/worker.py`) simply calls `Council.query_to_thread` (or a single member query if `--to` is passed) and writes to the same thread files, enabling the detached `--async` dispatch. Partial streams are therefore available under `.kd/branches/<branch>/threads/<thread-id>/.stream-<name>.md` while the agent is still running, but no current command reads or tails them—only the final Markdown messages are consumed by `list_messages`/`watch_thread`. citenone

**Thread persistence and status**

Thread persistence and metadata live in `src/kingdom/thread.py`. Each thread directory contains `thread.json` (members/pattern/created_at) plus sequentially numbered `<NNNN>-<sender>.md` files produced by `add_message`. Messages embed YAML frontmatter and Markdown body, and everything is normalized (sender names, safe filenames, retries). `list_messages` and `thread_response_status` sort and interpret these files, so both the `status` and `watch` commands operate purely on on-disk history. Thread roots sit under `.kd/branches/<branch>/threads/` (see `state.py` helpers like `branch_root`, `threads_root`, and `logs_root`), which means the same storage path is shared by council, peasant, and direct threads, and makes it easy to point a future UI at one directory per thread. citenone

**Status/watch streaming**

`watch_thread` (in `cli.py`) polls `list_messages` every 0.5 s, tracks which sequences it has rendered, and prints new `AgentResponse`s (using the same `render_response` Markdown panels) until all expected members respond or the timeout hits. `council_status` uses `thread_response_status` to compute pending vs. responded members per-thread and optionally prints log paths. There is no streaming subscription—`watch` simply re-reads the completed Markdown message files, and it ignores `.stream-*` files completely. citenone

**TUI infrastructure**

The existing UI is built entirely on `rich.Console` plus `Progress`/Markdown panels inside `src/kingdom/cli.py`. There is no persistent TUI framework (no `Prompt`, `Live`, or curses-style layout), so a richer chat UI would need to introduce new `Live`/`Layout` components or a separate TUI module that renders threads/messages based on the same thread directory data. Because all thread metadata lives on disk and the current renderers are simple `Console.print` calls, you can reuse the thread/socket helpers for any new TUI while replacing the `Progress` spinner with a live interface. citenone

**Next steps**

1. Tail the existing `.stream-<member>.md` files (located alongside `<NNNN>-*.md`) in `watch_thread` or a new UI layer so partial responses appear during long-running agent calls.
2. Build a dedicated `rich.Live`/`Panel` layout that subscribes to `list_messages`/`thread_response_status`, re-rendering as new files appear, to reuse the current storage while delivering a richer chat feel.
3. Consider exposing the async worker output (via `CouncilMember.log_path` and the `logs_root`) to make debugging/resuming easier in the new UI.
I confirmed the current council implementation uses file-backed threads and already produces per-member `.stream-*` files, but `watch` currently ignores those and only renders final message files. I’m now reading the redesign docs in this repo to compare your TUI idea against prior design directions and avoid repeating known dead ends.
I now have the SillyTavern group-chat mechanics (reply-order, pooled turns, auto-mode, force-talk/mute), which map well to your “broadcast then constrained group chat” idea. I’ll quickly check current local `kd` state (`status`, `council list/status`) so recommendations can account for real thread/status ergonomics, not just docs.
Current branch state is useful: there’s an active thread with only one member responded and two pending, which validates the “long spinner / delayed visibility” pain. I’m checking the thread contents and stream artifacts to pinpoint exactly what the user sees today vs what data already exists but is hidden.
I’ve confirmed the data path and also pulled the SillyTavern mechanics. I’m doing one final pass over the exact `cli.py` and `council/*.py` sections so I can ground each recommendation in concrete extension points and effort/risk.
One important detail surfaced: the Codex stream file is currently JSON event output (not plain prose), so blindly tailing `.stream-*` would be noisy unless normalized first. I’m checking the agent command/parse layer to distinguish what can stream cleanly vs what needs adaptation.
**Short Answer**
Your instinct is right: the biggest UX gap is not model quality, it’s interaction latency visibility. The current stack already captures live output, but the default UI path mostly hides it until completion. You can get most of the “natural feel” by fixing that first, then layering a real `kd chat` sidecar TUI, then optionally adding controlled group-chat turns.

**What’s Happening Today (Concrete)**
1. `kd council ask` writes your prompt to a thread and runs members in parallel (`src/kingdom/cli.py:340`, `src/kingdom/council/council.py:82`).
2. Member stdout is tee’d to `.stream-<member>.md` while running (`src/kingdom/council/council.py:111`, `src/kingdom/council/base.py:75`).
3. `watch_thread` polls finalized thread messages, not stream files (`src/kingdom/cli.py:717`), so you see spinner-then-dump.
4. In your current thread, this is visible right now: `kd council status --all` shows pending members while `.stream-codex.md` is huge and growing.

**Core Product Direction**
Build this as **one file-backed conversation runtime + two UX surfaces**:
1. `kd council ask/watch/status` stays as the scriptable CLI surface.
2. `kd chat` becomes an optional live UI surface over the exact same thread/stream files.
3. Keep tmux as viewport/hosting convenience, not transport (matches your docs’ direction).

That preserves reliability and avoids reintroducing old tmux-coupled fragility.

**Option Analysis**
1. Keep current workflow, add stream visibility only.
- Strengths: lowest effort, immediate pain relief, no mental model change.
- Weaknesses: still not “chat-like”; spinner UX still dominant; Codex stream is JSON events (`src/kingdom/agent.py:120`, `src/kingdom/agent.py:205`), so raw tailing is noisy unless normalized.

2. Three tmux panes (one per councillor).
- Strengths: feels closest to each native agent UI.
- Weaknesses: high pane management overhead, fragmented history, awkward broadcast/followup routing, poor portability.

3. Bring back `kd chat` as a dedicated sidecar TUI.
- Strengths: best UX/control tradeoff; single transcript; per-member live panels/bubbles; can run beside Claude Code.
- Weaknesses: requires separate pane/window; moderate build complexity; needs robust streaming normalization layer.

4. First-message broadcast then autonomous group chat (“engineers in a thread”).
- Strengths: richer deliberation; resolves conflicts between councillors without constant user nudges.
- Weaknesses: token/time blowups, groupthink risk, runaway loops, harder explainability.

**Recommendation (Phased)**
1. Phase 1: Fix “dead air” in existing flow.
- Add live streaming view to `watch` using current `.stream-*` files.
- Normalize streams per backend before rendering (especially Codex JSONL).
- Show “time-to-first-token” and per-member state transitions.

2. Phase 2: Add optional `kd chat` live UI.
- Single timeline + per-member visual identity.
- Input model: send to all / send to one.
- Persist everything to the same thread files.
- Keep this explicitly sidecar (separate pane) rather than trying to live inside Claude Code’s TUI.

3. Phase 3: Add controlled group-chat mode (opt-in).
- Start with independent first round always.
- Then enable bounded auto-turns with strict caps.

**Group-Chat Guardrails (Important)**
1. Default off.
2. Hard cap: max autonomous turns without user (for example 3-6).
3. Budget cap: token/time ceilings per round.
4. Speaker policy: round-robin or mention-driven, not unconstrained free-for-all.
5. Stop conditions: “no new info”, repeated consensus, or explicit `SKIP`.
6. Diversity protection: keep first round independent before inter-agent visibility.
7. Control knobs inspired by SillyTavern concepts: auto mode, activation strategy, mute/force-talk per member.

**What to Avoid**
1. Don’t make tmux panes the message bus.
2. Don’t let debate mode replace baseline broadcast-collect.
3. Don’t stream raw backend formats directly to users without normalization.
4. Don’t require `kd chat` for basic council usage.

**Bottom-Line Product Shape**
1. Baseline: `kd council ask` feels alive (no dead spinner).
2. Power mode: `kd chat` sidecar for rich continuous interaction.
3. Advanced mode: bounded debate/group-chat with explicit policies.

That gets you natural feel quickly without betting the system on a high-risk rewrite.

**Sources**
- `docs/third_party/llm-council.md`
- `docs/multi-agent-redesign.md`
- `docs/cli-skill-architecture.md`
- `src/kingdom/cli.py:340`
- `src/kingdom/cli.py:717`
- `src/kingdom/council/council.py:82`
- `src/kingdom/council/council.py:111`
- `src/kingdom/council/base.py:75`
- `src/kingdom/agent.py:120`
- `src/kingdom/agent.py:205`
- https://docs.sillytavern.app/usage/core-concepts/groupchats/
