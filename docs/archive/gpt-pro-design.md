The way to get unstuck here is to stop treating “multi‑agent” as one big feature and instead design three separable layers:

 1. Protocol (how agents communicate + how you persist everything)
 2. Runtime (how/where agents actually run: one-shot subprocess, long-lived worker, tmux window, etc.)
 3. UX (how the King observes + intervenes without the Hand mediating)

If you make the protocol file-backed and runtime-agnostic, you get your Hybrid (Option C) without “two code paths”: tmux becomes just a different launcher + viewer, not a different communication model.

Below is a concrete design that fits Kingdom’s existing patterns (git-tracked docs/tickets, operational state ignored, Typer/Rich CLI).

⸻

1) Core primitive: Agent Sessions with Mailboxes

Introduce a single concept that both council members and peasants use:

AgentSession

A session is a durable folder under .kd/runtime/sessions/<session-id>/ (operational, gitignored) containing:
 • session.json (metadata + backend resume token)
 • inbox/ (messages to the agent)
 • outbox/ (agent replies)
 • events.ndjson (append-only progress + heartbeat events)
 • logs/ (raw stdout/stderr from subprocess calls, if any)

This is the “bus”. Everything else becomes a wrapper around it.

Message format

Keep it consistent with your ticket format: Markdown with YAML frontmatter.

Example inbox/msg-20260207-153012Z-7f3a.md:

---
id: msg-20260207-153012Z-7f3a
thread: council-20260207-ux-auth
from: king
to: council.codex
created_at: 2026-02-07T15:30:12Z
kind: prompt
reply_required: true
refs:

- .kd/branches/feature-auth/design.md
- .kd/branches/feature-auth/breakdown.md

---

Propose 2 alternative approaches for auth token storage.
Include tradeoffs, failure modes, and tests I'd want.

Agent replies in outbox/ with same frontmatter + reply_to.

Why this matters:
 • Works in CLI-only mode (files + kd watch)
 • Works in tmux mode (each session can be “watched” in a window)
 • Enables supervision (King can drop messages into any peasant inbox)
 • Enables agent-to-agent supervision later (a foreman agent can read peasant outboxes)

⸻

1) The “Agent Worker Loop” (one loop, many runtimes)

Implement a small executable loop:

kd agent worker --session <id>

Responsibilities:

 1. Claim next message from inbox/ (atomic rename into processing/)
 2. Run the backend (claude/codex/cursor/etc.) with:
 • prompt content
 • session resume token (if any)
 • any referenced files
 3. Write reply to outbox/
 4. Append to events.ndjson (started, finished, error, heartbeat)

This “worker” is what you run:
 • as a background subprocess (CLI-only)
 • or inside a tmux window (observable)
 • or even interactively attached in the foreground

Key detail: avoid fragile tmux send-keys

Don’t “poke” an interactive agent mid-flight.

Instead:
 • tmux windows run kd agent worker ...
 • the worker prints status + tail logs
 • it polls inbox (or uses file watch later)

tmux becomes a glass wall: you watch, you don’t inject.

⸻

1) Council becomes “N agent sessions + a thread id”

Right now kd council ask is “spawn 3 subprocesses and wait”.

You can keep that UX, but reframe internally:

CouncilThread

A thread is just:
 • a thread-id
 • one AgentSession per council member
 • a run folder for saved markdown output (your current behavior)

Suggested layout:
 • .kd/runtime/threads/council-20260207-ux-auth/thread.json
 • .kd/runtime/threads/.../members/claude.json (points to session id)
 • .kd/branches/<branch>/council/<thread-id>/ (git-tracked transcript if you want)
 • 0001.king.md
 • 0002.claude.md
 • 0003.codex.md
 • 0004.cursor.md

You keep the “King reads directly” principle by writing raw responses to those markdown files with minimal formatting.

Commands that fall out naturally
 • kd council start → creates thread + sessions (but doesn’t have to run anything yet)
 • kd council ask "..." → writes one message per member inbox, waits for outbox replies, prints panels
 • kd council ask --member codex "..." → targeted follow-up
 • kd council open → opens the transcript folder (or prints paths)
 • kd council watch → Rich Live view showing which members have replied (no tmux required)

Where “iterative discussion” comes from

Iterative doesn’t require a chat room. It requires:
 • stable thread id
 • per-member resume token persisted
 • a clean “send follow-up to X” flow

That gives you:
 • ask all → read responses
 • ask codex follow-up → read response
 • ask claude follow-up → read response
 • ask all again with refined prompt

All without ever sharing context between members.

⸻

1) Peasants are the same thing, with a ticket-shaped harness

A “peasant” is just an AgentSession plus extra metadata:
 • ticket id
 • worktree path
 • branch name
 • “goal” (ticket acceptance criteria)

Worktree + branch strategy (practical default)

Because git worktrees can’t share the same branch concurrently, make each peasant own a ticket branch:
 • Feature branch: feature/auth
 • Ticket branches:
 • feature/auth/ticket-KD-014
 • feature/auth/ticket-KD-015

Flow:

 1. kd peasant start KD-014
 • creates branch feature/auth/ticket-KD-014 from feature/auth
 • creates worktree .kd/runtime/worktrees/KD-014/
 • starts an agent worker in that directory
 2. Peasant produces commits on its ticket branch
 3. King merges ticket branches back to feature branch in dependency order

The PeasantHarness (thin wrapper)

Instead of sending arbitrary prompts, peasants consume a structured “ticket start” message:

---

kind: ticket_start
ticket: KD-014
branch: feature/auth
worktree: .kd/runtime/worktrees/KD-014
acceptance_criteria_ref: .kd/branches/feature-auth/tickets/KD-014.md
---

Implement KD-014. Follow acceptance criteria. Commit logically. Run tests.
If blocked, write a BLOCKED report with what you need.

The harness then:
 • checks out correct branch in the worktree
 • runs the backend agent with a consistent scaffold prompt
 • periodically emits events.ndjson updates like:
 • phase=plan
 • phase=implement
 • phase=test
 • blocked=...
 • ready_for_review=true

Supervision UX (CLI-only works; tmux enhances)
 • kd peasant status → tabular snapshot
 • kd peasant watch → Rich Live dashboard (updating)
 • kd peasant logs KD-014 -f → tail
 • kd peasant msg KD-014 "Focus on tests first" → writes into inbox
 • kd peasant stop KD-014 → sends “stop” message, then kills if needed

And if tmux is available:
 • kd peasant start KD-014 --tmux → opens/uses tmux session and a window named peasant-KD-014
 • King can jump in visually and see what it’s doing

⸻

1) How this resolves your CLI vs tmux tension

You described Option C’s downside as “two code paths.”

You can dodge that by making tmux only a runtime/launcher:

Single protocol, single worker loop
 • Always: files + sessions
 • Always: kd agent worker processes inbox/outbox
 • Sometimes: launch workers in tmux windows instead of background subprocesses

So:
 • CLI-only mode = worker runs detached, you observe via kd watch and logs
 • tmux mode = worker runs inside a tmux window, you observe via tmux (and optionally still via kd watch)

No divergence in how messages are routed or persisted.

⸻

1) Concrete command surface (minimal but complete)

Here’s a compact set that covers both council + peasants without conceptual duplication.

Generic
 • kd agent ps
 • kd agent start <agent-name> [--bg|--tmux] [--workdir PATH]
 • kd agent send <session-or-name> --thread T "message..."
 • kd agent wait <session> [--timeout ...]
 • kd agent logs <session> [-f]
 • kd agent stop <session>
 • kd agent attach <session> (tmux only: jumps to window)

Council wrappers
 • kd council start [--thread NAME]
 • kd council ask "prompt" [--thread ID] [--member NAME]
 • kd council watch [--thread ID]
 • kd council open [--thread ID]

Peasant wrappers
 • kd peasant start <ticket-id> [--tmux|--bg] [--agent codex]
 • kd peasant start --ready [--max N] (spawns from kd ticket ready)
 • kd peasant status
 • kd peasant watch
 • kd peasant msg <ticket-id> "..."

⸻

1) Implementation notes that will save you pain

A) Message claiming must be atomic

Use rename to a processing/ folder. That prevents double-processing when you later add a “foreman” or multiple worker processes.

B) Add heartbeats for monitoring

Have each worker append a heartbeat event every ~2–5 seconds (or touch a file). Your dashboard becomes reliable without parsing logs.

C) Store backend resume state in session.json

Each backend differs:
 • claude might return a resume handle
 • codex might use a session id
 • cursor agent might have its own token

Hide that behind CouncilMember.session_state.

D) Make “watch” first-class even in CLI-only mode

A Rich Live dashboard (kd watch / kd peasant watch) gets you 70% of “tmux visibility” without tmux.

tmux then becomes about:
 • unmediated access
 • multiple full terminals
 • quick switching

E) Keep git-tracked artifacts separate from runtime

A clean split that matches your philosophy:
 • Git-tracked:
 • .kd/branches/<branch>/{design.md,breakdown.md,tickets/*}
 • .kd/branches/<branch>/council/<thread-id>/*.md (optional, but nice)
 • Gitignored operational:
 • .kd/runtime/** (sessions, logs, pids, worktrees)

⸻

1) A sane build order (so you don’t boil the ocean)

Step 1: Sessions + worker loop (no peasants yet)
 • Implement .kd/runtime/sessions
 • Implement kd agent worker
 • Re-implement kd council ask on top of “send messages + wait for outbox”

You’ll immediately get:
 • persistent council threads
 • follow-ups
 • better observability

Step 2: CLI-only monitoring
 • kd agent ps
 • kd council watch (Rich Live)
 • store transcripts in .kd/branches/.../council/...

Step 3: Peasant scaffolding (still CLI-only)
 • worktree creation per ticket branch
 • kd peasant start starts worker in background with ticket harness prompt
 • kd peasant status/watch

Step 4: tmux runtime
 • kd tmux ensure-session
 • kd agent start --tmux = run the same worker loop in a tmux window
 • kd agent attach

At this point Option C is real, but you didn’t fork your architecture.

⸻

The “one sentence” design choice

Make .kd/runtime/sessions/* a file-backed message bus, run a single kd agent worker loop per agent, and treat tmux as an optional launcher/viewer for that loop—not a transport.

That gives you:
 • iterative multi-perspective council discussions (threaded + resumable)
 • parallel ticket execution (peasants) with supervision hooks
 • CLI-only portability
 • tmux visibility when desired
 • no duplicated orchestration logic

If you want, I can also sketch the exact session.json schema + a minimal events.ndjson event taxonomy that will make kd watch feel great without becoming a full TUI.

---

Claude Code “Agent Teams” is basically an existence proof that your Option C / hybrid instinct is right — but it also highlights a few traps you’ll want to avoid in Kingdom.

Here’s how I’d read it in the context of your design goals (multi-perspective design discussions + parallel ticket execution under King supervision).

What Teams is, structurally

Anthropic’s model is:
 • One lead session that coordinates, assigns tasks, and synthesizes results.  ￼
 • Multiple teammate sessions, each with its own context window, that can message each other directly (and you can message them directly too).  ￼
 • A shared task list with states (pending / in progress / completed) and dependencies, plus file locking to avoid two workers claiming the same task.  ￼
 • A mailbox concept for messaging (they don’t fully specify implementation details in the docs, but it’s explicitly part of the architecture).  ￼
 • Two UI modes:
 • “In-process” multiplexing inside one terminal
 • “Split panes” that require tmux or iTerm2  ￼
 • Quality gates via hooks on teammate idle and task completion, where exit code 2 sends feedback and blocks the state transition (idle or complete).  ￼

They also explicitly warn that agent teams are experimental with known limitations in session resumption, task coordination, and shutdown.  ￼

Why this is relevant to Kingdom

1) It validates your “tmux is for watching, files are for talking” framing

Teams is explicitly built around:
 • a task list
 • a mailbox
 • and an optional pane-based display layer (tmux / iTerm2)  ￼

That’s extremely close to the “protocol-first, runtime-agnostic, tmux as viewer” architecture you want Kingdom to converge on.

If you implement “AgentSession + inbox/outbox + events” in Kingdom, you’re building the same shape — just not hardwired to Claude.

1) It surfaces two primitives Kingdom should probably steal outright

A. “Claiming” is a first-class concurrency problem
Teams calls out that task claiming uses file locking to prevent races when multiple teammates try to claim the same task.  ￼

That maps perfectly to your ticket dependency graph + “ready” list. In Kingdom terms:
 • kd ticket ready produces the candidate set
 • “claim” must be atomic (lock or atomic rename) so two peasants don’t pick the same ticket
 • “release” / “complete” must be idempotent and crash-safe

This is the stuff that makes parallel peasants actually work.

B. Quality gates that can block completion are gold
Their hook semantics are exactly what you’ll want for peasants:
 • TeammateIdle: before a worker goes idle, you can force checks and send feedback (exit 2 keeps them working).  ￼
 • TaskCompleted: before a task can be marked complete, run tests/lint/etc; exit 2 blocks completion and feeds feedback back to the model.  ￼

That is a really clean pattern for:
 • “peasant says ticket done”
 • Kingdom runs acceptance criteria gates (tests, formatting, diff checks, maybe “no TODOs added”)
 • If fail → automatically bounce the peasant back with concrete feedback and keep ticket “in progress”

You can implement this in Kingdom without needing an integrated TUI.

1) It’s also a warning about resumption and cleanup

Their limitations section is basically a checklist of what can go wrong when orchestration state isn’t fully durable:
 • teammates may not resume after /resume in some modes  ￼
 • task status can lag / fail to flip, blocking dependency chains  ￼
 • shutdown can be slow because workers finish their current tool call  ￼

Kingdom can do better if you keep orchestration state in your own .kd/runtime/** event log and treat agent backends as unreliable processes that might disappear mid-task.

That aligns with your “git-backed artifacts + operational state ignored by git” model.

Where Teams diverges from Kingdom’s core principles

This is the important part: Teams is not a drop-in replacement for what you’re building.

Vendor lock-in

Teams coordinates Claude Code instances. Your council goal is specifically “multiple different perspectives” across different agent systems (Claude, Codex, Cursor). Teams can’t help with that except within Claude’s model ecosystem.  ￼

Lead synthesis vs “King reads raw”

Teams is designed around the lead synthesizing results.  ￼
You can message teammates directly (so raw access exists), but the default workflow is still “lead coordinates and synthesizes.”

Your Kingdom principle is almost the opposite: the King reads council outputs directly and synthesizes mentally, with minimal mediation. So for the council, you probably don’t want a lead agent that summarizes by default.

(But for peasants, a “lead/foreman” does make sense.)

Inter-agent communication can create groupthink

Teams explicitly encourages teammates to message each other directly and “share and challenge findings.”  ￼

That’s great for debugging and converging on a truth, but it’s the opposite of “independent parallel perspectives” when you’re trying to avoid anchoring.

So I’d treat “teammates can talk” as a mode, not the default, in Kingdom:
 • Council mode: no cross-agent messaging (pure independence)
 • Debate mode: explicit cross-messaging allowed (for competing hypotheses)
 • Peasant mode: limited messaging (mostly peasant ↔ King, maybe peasant ↔ foreman)

State location

Teams stores team config and task lists under ~/.claude/....  ￼
Kingdom’s “artifact in repo history” value prop is that the important stuff lives in .kd/ inside the repo, not only in a per-user home directory.

So even if you use Claude Teams operationally, you’ll still want Kingdom’s git-tracked design/breakdown/tickets/work logs.

My practical take: what to do with this in Kingdom

If I were you, I’d treat Agent Teams as:

1) A strong validation of the primitives you should build

Especially:
 • mailbox/session abstraction
 • shared task list with deps
 • atomic claim
 • quality gates that can block completion

Teams basically proves that those are the winning abstractions.  ￼

1) A hint that “tmux as an optional visibility layer” is a sane compromise

Teams defaults to “auto” and uses split panes when already in tmux, in-process otherwise.  ￼

That’s very close to your Option C:
 • CLI-only remains viable
 • tmux is an opt-in “show me everything live” mode

The difference is: Teams can multiplex in-process inside Claude Code; Kingdom probably won’t want to build that kind of interactive multiplexing (Rich Live dashboards are likely enough).

1) Something you might integrate as a backend later — but not as your core architecture

If you want a “fast path” for Claude-only users, you could add a Kingdom backend like:
 • kd council ask --backend claude-teams
 • kd peasant start --backend claude-teams

…but you’d be constrained by Teams’ rules (one team per session, no nested teams, etc. — see limitations and architecture).  ￼

So I’d only do this after Kingdom’s protocol + orchestration is already stable. Otherwise you risk making Kingdom’s design contort around an external feature’s lifecycle quirks.

A quick mapping table

Claude Teams concept Kingdom analog (recommended) Notes
Team lead coordinates + synthesizes  ￼ Optional Foreman agent Good for peasants; for council, keep King-as-synthesizer
Teammates are independent sessions  ￼ Peasants / council members as AgentSessions Same shape
Shared task list + deps  ￼ Ticket graph + kd ticket ready Add atomic claim + task state
File locking for claiming  ￼ Atomic rename / file lock in .kd/runtime Required for parallel
Split panes via tmux  ￼ kd ... --tmux attach/view mode Viewer, not transport
Plan approval mode  ￼ “plan-only” ticket phase until approved Great for risky tickets
Hooks for quality gates  ￼ kd hooks on TicketCompleted/PeasantIdle Exit code semantics are a good pattern

Bottom line
 • Teams is very aligned with your direction: mailbox + task list + optional tmux is exactly the architecture that scales.  ￼
 • But it’s solving a different “design discussion” problem: it’s optimized for collaboration and convergence among Claude sessions, whereas your council is optimized for independent viewpoints across different tools/models.  ￼
 • The two biggest takeaways for Kingdom are:
 1. treat task claiming + deps as a concurrency primitive (not “just status”),  ￼
 2. implement quality gates that can block completion and send feedback (their hook pattern is excellent).  ￼

If you want, I can translate Teams’ task-list mechanics into a concrete Kingdom file schema (e.g., .kd/runtime/tasks/*.json or markdown frontmatter) + the exact atomic claim algorithm and the minimal Rich “live dashboard” view that makes CLI-only feel good.
