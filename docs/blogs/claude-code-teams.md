# Claude Code Agent Teams: What It Means for Kingdom

Claude Code "Agent Teams" is an existence proof that Kingdom's architectural instincts are right. There's significant convergence — and a few places where they made different choices worth learning from.

## What Teams Is

Anthropic's model:

- **One lead session** that coordinates, assigns tasks, and synthesizes results.
- **Multiple teammate sessions**, each with its own context window, that can message each other directly (and you can message them directly via `Shift+Up/Down`).
- **A shared task list** with states (pending / in progress / completed) and dependencies, plus file locking to prevent two workers from claiming the same task.
- **A mailbox concept** for inter-agent messaging.
- **Two UI modes**: "in-process" multiplexing inside one terminal, or "split panes" requiring tmux or iTerm2.
- **Quality gates** via hooks on teammate idle (`TeammateIdle`) and task completion (`TaskCompleted`), where exit code 2 sends feedback and blocks the state transition.

They explicitly warn that agent teams are experimental with known limitations in session resumption, task coordination, and shutdown.

## Where Teams Validates Kingdom's Design

**Files as coordination, not terminal I/O.** Their task list is file-based (`~/.claude/tasks/{team-name}/`), team config is a JSON file that teammates discover by reading it, and task claiming uses file locking. This is exactly the "files are how they talk" principle. They arrived at the same answer independently.

**Tmux as optional viewport.** Their default is in-process (no tmux), with split panes as opt-in for visibility. Same conclusion — tmux is where you watch, not how they communicate. They explicitly call out the same limitations: doesn't work in VS Code terminal, Windows Terminal, etc. This strongly supports the "protocol-first, runtime-agnostic, tmux as viewer" architecture Kingdom is converging on.

**Task dependencies with automatic unblocking.** Tasks have dependency tracking; when a task completes, blocked tasks unblock automatically. This maps directly to Kingdom's ticket `deps` system. The dependency-ordered ticket model is the right foundation.

**Direct access to any agent.** `Shift+Up/Down` to message a teammate directly, bypassing the lead, is the same principle as `kd say @claude` — the King doesn't have to route everything through a mediator.

## Where Teams Diverges from Kingdom

**The lead is an agent, not the human.** This is the biggest architectural divergence. In Teams, the "lead" is a Claude Code session that coordinates — it spawns teammates, assigns tasks, synthesizes results. The human sits above the lead. In Kingdom, the King (human) *is* the coordinator, and the Hand is just a messenger.

Their approach is convenient — you can say "go investigate this bug" and walk away. But it costs you the thing Kingdom explicitly optimizes for: **the King reading responses directly without mediation**. Their lead synthesizes findings, which means the human gets a filtered view. Kingdom's design says that filtering is exactly what you *don't* want from a council. (Though for peasants, a lead/foreman role does make sense.)

**Automatic message delivery vs. polling.** Their teammates send messages that arrive automatically at the lead. Kingdom's design has agents write to outboxes and the King runs `kd read` to check. Their approach is more real-time but couples agents more tightly. Kingdom's pull-based model is simpler and more robust — nothing breaks if you don't check messages for a while.

**Inter-agent communication can create groupthink.** Teams encourages teammates to message each other and "share and challenge findings." That's great for debugging and convergence, but it's the opposite of "independent parallel perspectives" when you're trying to avoid anchoring. In Kingdom, this should be a mode, not the default:
- **Council mode**: no cross-agent messaging (pure independence)
- **Debate mode**: explicit cross-messaging allowed (competing hypotheses)
- **Peasant mode**: limited messaging (peasant-to-King, maybe peasant-to-foreman)

**Spawn prompt instead of persistent context.** Teammates get a spawn prompt from the lead but don't inherit conversation history — one-shot context injection. Kingdom's message-based system is richer: an advisor in a council session accumulates context through `--resume`, so follow-up questions build on prior turns. Their model treats teammates as disposable; Kingdom treats advisors as persistent conversation partners.

**Vendor lock-in.** Teams coordinates Claude Code instances only. Kingdom's council goal is specifically "multiple different perspectives" across different agent systems (Claude, Codex, Cursor). That's the whole point: you want disagreement, not three copies of the same model.

**State location.** Teams stores config and task lists under `~/.claude/`, which is ephemeral. Kingdom's `.kd/` directory lives in the repo, so design discussions, ticket breakdowns, and work logs become part of the project's git history.

## Ideas Worth Stealing

**Plan-then-implement gating.** Before a peasant starts coding a ticket, it writes a plan, sends it as an escalation, and waits for the King to approve. This is a natural fit for Kingdom's escalation mechanism — just add a `plan-review` escalation type that blocks the peasant until approved. This prevents the worst failure mode of autonomous agents: silently building the wrong thing for 20 minutes.

**Delegate mode as an explicit state.** Toggling the lead into "coordination only" mode is useful. For Kingdom, this could be a hint to the Hand: "you're in council mode right now, just run `kd` commands, don't start coding." Not enforced mechanically, but a useful convention.

**Quality gates that block completion.** Their hook semantics are excellent for peasants:
- Peasant says ticket done
- Kingdom runs acceptance criteria gates (tests, formatting, diff checks, maybe "no TODOs added")
- If fail: automatically bounce the peasant back with concrete feedback, keep ticket "in progress"

Kingdom could implement hooks on channel events — `on_escalation`, `on_completion`, `on_status_change` — that run arbitrary scripts.

**Atomic task claiming.** Task claiming must be treated as a first-class concurrency problem. In Kingdom terms: `kd ticket ready` produces the candidate set, "claim" must be atomic (lock or atomic rename) so two peasants don't pick the same ticket, and "release"/"complete" must be idempotent and crash-safe.

**Task sizing guidance.** Their "5-6 tasks per teammate" heuristic is practical wisdom worth encoding. A peasant working one massive ticket for an hour without check-ins is a problem. Breaking tickets smaller gives the King more intervention points.

**Resilience lessons.** Their limitations section is a checklist of what goes wrong when orchestration state isn't fully durable: teammates may not resume, task status can lag and block dependency chains, shutdown can be slow. Kingdom can do better by keeping orchestration state in `.kd/runtime/` and treating agent backends as unreliable processes that might disappear mid-task.

## What Kingdom Does Better

**The council pattern has no equivalent.** Teams is built for parallel *work*, not parallel *thinking*. There's no native way to say "give me three independent perspectives on this design and let me drill into each one." Kingdom's `kd say @claude` / `kd say @codex` / `kd read` flow is purpose-built for this.

**Heterogeneous agents.** Different models with different strengths and blind spots — that's the whole point of the council.

**Git-tracked design history.** The council conversation that shaped a design decision is preserved alongside the code it produced.

## Concept Mapping

| Claude Teams | Kingdom Analog | Notes |
|---|---|---|
| Team lead coordinates + synthesizes | Optional Foreman agent | Good for peasants; for council, keep King-as-synthesizer |
| Teammates as independent sessions | Peasants / council members as AgentSessions | Same shape |
| Shared task list + deps | Ticket graph + `kd ticket ready` | Add atomic claim + task state |
| File locking for claiming | Atomic rename / file lock in `.kd/runtime` | Required for parallel peasants |
| Split panes via tmux | `kd ... --tmux` attach/view mode | Viewer, not transport |
| Plan approval mode | "plan-only" ticket phase until approved | Great for risky tickets |
| Hooks for quality gates | `kd hooks` on TicketCompleted/PeasantIdle | Exit code semantics are a good pattern |

## Bottom Line

Teams validates the core infrastructure choices — file-based coordination, mailbox + task list, tmux as optional viewport, dependency-tracked tasks. But it's solving a different problem: parallelizing *implementation work* within a single tool (Claude Code). Kingdom is solving multi-*model* design consultation and human-supervised parallel execution across tools.

The two biggest takeaways for Kingdom:
1. Treat task claiming + deps as a concurrency primitive, not just status tracking.
2. Implement quality gates that can block completion and send feedback.

Teams could potentially be integrated as a backend later (`kd council ask --backend claude-teams`), but only after Kingdom's own protocol and orchestration are stable. Otherwise you risk contorting the design around an external feature's lifecycle quirks.
