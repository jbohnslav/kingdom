# Gastown: Analysis for Kingdom

Gastown (Gas Town) is a multi-agent orchestration system focused on coordinating many Claude Code–style agents with persistent work tracking. It uses a workspace model (“Town”) with per-project “Rigs,” and persists agent work via git worktrees (“Hooks”) and Beads-based issue tracking.

Source: `third-party/gastown/`

---

## Core Concepts

- **Mayor**: Primary coordinator agent with the full workspace context.
- **Town**: Root workspace directory containing all rigs and configuration.
- **Rig**: Project container backed by a git repo.
- **Crew**: Your personal workspace inside a rig.
- **Polecats**: Ephemeral worker agents that pick up and complete tasks.
- **Hooks**: Git worktree–backed persistence for agent work state.
- **Beads / Convoys**: Structured issue tracking and work bundling.

## Relevance to Kingdom

- **Persistent state via git** maps to Kingdom’s `.kd/` run state, but Gastown pushes persistence into git worktrees and Beads. Could inspire more robust ticket state storage for multi-agent scaling.
- **Role separation (Mayor/Crew/Polecats)** mirrors Kingdom’s Hand/Peasant model. Mayor could map to Hand, Crew to Peasant sessions, Polecats to short-lived workers.
- **Multi-agent scale (20–30)** is far beyond MVP scope but provides a target architecture for future “parallel peasants”.

## Potential Patterns Worth Adopting

- **Work persistence in git**: Hooks-like worktrees could preserve intermediate changes between agent runs.
- **Beads as work ledger**: A structured issue store could complement or replace `.tickets/` for richer orchestration.
- **Workspace-first model**: A Town-style root could formalize multi-project operation if Kingdom expands.

## Notes / Risks

- Gastown is a full system with its own CLI (`gt`) and concepts; adopting wholesale would be heavy.
- Kingdom’s MVP should stay minimal; treat Gastown as design inspiration rather than a dependency.
