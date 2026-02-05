# Gastown Review Plan (for Kingdom)

Goal: learn from Gastown’s codebase to decide whether Kingdom should adopt it, fork ideas, or stay independent while remaining simpler and cleaner.

## Checklist

- [x] Read `third-party/gastown/README.md` and capture architecture + CLI mental model.
- [x] Scan `third-party/gastown/docs/overview.md` and `docs/reference.md` for core workflows and command surface.
- [x] Review `third-party/gastown/docs/design/*` for system components and failure modes.
- [x] Review `third-party/gastown/docs/concepts/*` for conceptual model (agents, persistence, lifecycles).
- [x] Inspect `third-party/gastown/cmd/gt` and high-level `internal/` packages for subsystem boundaries.
- [ ] Identify Gastown features Kingdom lacks but might want (and which are essential vs optional).
- [ ] Identify Gastown complexity we should avoid for MVP or long-term simplicity.
- [ ] Map Gastown roles/state to Kingdom’s Hand/Peasant/.kd/tk tickets.
- [ ] Produce a “Use Gastown vs Kingdom” decision summary.
- [ ] Propose “Kingdom simplifications” inspired by Gastown.

## Progress Log

- 2026-02-03: Created review plan and checklist.
- 2026-02-03: Read `README.md`, `docs/overview.md`, and `docs/reference.md`.
  - Key focus: Town/Rig model, role taxonomy (Mayor/Deacon/Witness/Refinery/Crew/Polecats), and Beads routing.
- 2026-02-03: Reviewed design docs (e.g., `docs/design/architecture.md`) and concepts (`concepts/polecat-lifecycle.md`, `concepts/convoy.md`).
  - Notable patterns: two-level beads (town+rig), worktree-based polecats, explicit convoy tracking, and self-cleaning workers.
- 2026-02-03: Scanned CLI entrypoints and internal packages.
  - `gt` uses Cobra; command surface is very broad (rig/crew/polecat/mayor/convoy/sling/etc).
  - `gt sling` is the unified dispatch primitive (bead or formula, auto-convoy, auto-spawn polecats).
  - `gt convoy` is a first-class tracking dashboard for multi-issue work.
  - Workspace detection is robust to worktree deletion (fallback via `GT_TOWN_ROOT`).
- 2026-02-03: Read operational-state and watchdog design docs.
  - State changes are modeled as events + labels (immutable history + current-state cache).
  - Watchdog chain (daemon→boot→deacon→witness/refinery) provides resilient recovery.
  - Convoy completion is designed to become event-driven, with redundant observers.

## Mapping to Kingdom (MVP)

- **Town / Rig** → Kingdom has a single-repo `.kd/` run; Gastown’s multi-rig containerization is beyond MVP.
- **Mayor** → Hand (primary human-facing coordinator).
- **Crew** → Peasant (long-lived or task-focused worker).
- **Polecats** → Not in MVP; conceptually “ephemeral peasants” spawned per ticket.
- **Hooks / Worktrees** → Kingdom already uses worktrees for `kd peasant`, but without the full lifecycle tooling.
- **Beads / Convoys** → Kingdom uses `tk` markdown tickets; Gastown’s beads+convoys provide richer tracking and identity.
- **Deacon/Witness/Refinery** → No direct equivalent in MVP; maps to future automation (health, merge queue).

## Patterns Worth Copying (Small, High-Value)

- **Unified dispatch command**: A single “assign work” surface (`gt sling`) reduces cognitive load. Kingdom could keep `kd peasant` but add a simple `kd assign` wrapper for tickets.
- **Auto-tracking of work**: Convoy auto-creation gives a dashboard for “what’s in flight”. Kingdom could implement a lightweight “run ledger” in `.kd/runs/<feature>/state.json`.
- **Worktree lifecycle clarity**: Explicit states and cleanup rules for workers reduce confusion. Kingdom can document a simpler lifecycle (start → work → done → cleanup).
- **Workspace detection fallback**: Environment fallback (like `GT_TOWN_ROOT`) for deleted worktrees is a nice reliability improvement.
- **Events + labels**: If Kingdom grows, storing state transitions with a current-state cache is a clean pattern (minimal version: append-only log + current state summary).

## Patterns to Avoid (for Simplicity)

- **Multi-tier watchdog chain**: Powerful, but heavy. MVP doesn’t need daemon/boot/deacon orchestration.
- **Beads routing and prefixes**: Valuable at scale, but likely too much infra for Kingdom’s current scope.
- **Convoy lifecycle complexity**: Event-driven, redundant observers, ownership semantics are overkill for now.
- **Large command surface**: Gastown’s CLI breadth is a maintenance cost; Kingdom should keep commands minimal.

## Decision Notes: “Use Gastown vs Kingdom”

**When Gastown wins:**
- You need many concurrent agents (10–30) across multiple repos.
- You want durable, structured issue tracking (Beads) and a merge-queue/refinery pipeline.
- You can afford the operational complexity and Go-based CLI surface.

**When Kingdom wins:**
- You want a minimal, repo-local workflow with light state.
- You prefer simple, explicit flow over automation-heavy orchestration.
- You’re iterating on UX and want to keep the system hackable.

**Migration cost:**
- Switching to Gastown would require adopting Beads, Town/Rig workspace, and `gt` CLI conventions.
- Kingdom’s `.kd/` + `tk` approach would be superseded, not integrated, unless you build a bridge.

## Recommendation (Current State)

- **Do not replace Kingdom with Gastown** for MVP. The operational surface and multi-agent machinery are far beyond the current scope.
- **Adopt selective patterns**: unified dispatch semantics, clearer worker lifecycle, and minimal “in-flight work” tracking.
- **Re-evaluate later** if Kingdom needs multi-repo orchestration, agent health automation, or a merge-queue.
