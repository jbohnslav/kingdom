`# Kingdom CLI Design

The `kd` command is your interface to the Kingdom workflow. You (the King) talk to a Hand who manages the entire process - design, planning, development, review, and merge.

## Core Philosophy

- **One point of contact:** You (the King) talk to the Hand via `kd chat`. The Hand manages the workflow, coordinates Peasants, handles blockers, and asks you questions when decisions are needed.
- **Council when it matters:** Council (multi-model consensus) is automatic for design, plan, and code review phases. For mid-work conversations, you just talk to the Hand - it can invoke the Council as a tool if needed.
- **Autopilot with oversight:** After plan approval, tickets flow through dev → test → review → merge automatically. The Hand handles blockers and escalates to you when needed.
- **Transparent commands:** Phase commands (`kd design`, `kd plan`, etc.) exist and are visible. The Hand calls them; you can too if you want direct control.

## Commands

### King Commands (your interface)

| Command | Description |
|---------|-------------|
| `kd start <feature>` | Begin a new feature. Creates branch, initializes state, starts tmux server and Hand. |
| `kd chat` | Talk to the Hand. Your main interaction point for the entire workflow. |
| `kd council` | Talk to the Council directly (multi-model consensus). Use for important decisions outside the normal flow. |
| `kd status` | Read-only dashboard: current phase, ticket counts, what needs you. |
| `kd attach <target>` | Watch/intervene in a specific pane: `hand`, `council`, `peasant-1`, `ticket-nw-5c46` |
| `kd approve <ticket>` | Quick unblock without opening chat. |

### Phase Commands (called by Hand, available to King)

| Command | Description |
|---------|-------------|
| `kd design` | Enter or return to design phase (uses Council). |
| `kd plan` | Enter planning phase (uses Council). |
| `kd dev` | Start development Peasants. |
| `kd test <ticket>` | Run test phase on a ticket (fresh agent). |
| `kd review <ticket>` | Run review phase on a ticket (uses Council). |
| `kd merge` | Merge feature branch to main. |

The Hand calls these commands to advance the workflow. You (the King) can call them directly for manual control, but normally you just talk to the Hand.

## The Hand

The Hand is a persistent Claude Code session that:

- Has full context: design doc, tickets, Peasant status, conversation history
- Manages the workflow by calling phase commands
- Monitors Peasants and handles blockers
- Asks you (the King) questions when human judgment is needed
- Can add/modify tickets, pause Peasants, revise designs mid-flight
- Uses `tk` commands to manage tickets

**You don't need to remember what command to run next.** The Hand tells you what's happening and asks when it needs input.

Example interaction:

```
You: Let's start working on OAuth token refresh

Hand: I'll set that up. Creating branch feature/oauth-refresh.
      Let's start with design. What are the key requirements?

You: Users should stay logged in, tokens refresh automatically,
     and we need to handle the case where refresh fails.

Hand: Got it. I'm routing this to the Council for design.
      [Council runs - you see 3 model responses + synthesis]

      Here's the consolidated design. Claude suggested JWT with
      sliding expiration. GPT found that our auth provider supports
      refresh token rotation. Gemini raised a good point about
      offline scenarios. I've incorporated all three.

      Want to adjust anything, or should we move to planning?

You: Looks good, let's plan it out.

Hand: [runs kd plan - Council generates tickets]
      I've broken this into 4 tickets:
      - nw-5c46: Add refresh token storage
      - nw-7b89: Implement auto-refresh logic (depends on nw-5c46)
      - nw-3a21: Handle refresh failures
      - nw-8d12: Add retry with backoff

      How many Peasants do you want?

You: 3 Peasants, let's go.

Hand: [runs kd dev]
      Started 3 Peasants. nw-5c46 is in progress, nw-3a21 and nw-8d12
      are queued. I'll let you know when something needs your attention.
```

## The Council

The council is multi-model consensus mode:

1. Your prompt goes to 3 models in parallel (Claude, GPT, Gemini)
2. You see all three responses
3. A synthesis model combines the best insights
4. You can direct the synthesis: "Use Claude's approach but incorporate GPT's API suggestion"

**When Council is automatic:**
- Design phase - always uses Council
- Plan phase - always uses Council
- Code review - always uses Council (per-ticket)

**When Council is optional:**
- Mid-work chat with Hand - Hand decides when to invoke it
- Direct `kd council` command - you invoke it explicitly

**Tmux layout during council mode:**

```
┌─────────────────┬─────────────────┬─────────────────┐
│     Claude      │      GPT        │     Gemini      │
│                 │                 │                 │
│  (read-only)    │  (read-only)    │  (read-only)    │
│                 │                 │                 │
├─────────────────┴─────────────────┴─────────────────┤
│                    Synthesis                        │
│                                                     │
│  Your interaction happens here. Reference the       │
│  model outputs above and direct the synthesis.      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Ticket Management via `tk`

The Hand and Peasants use the `tk` CLI for all ticket operations:

```bash
# Hand creates tickets during planning
tk create "Add refresh token storage" -p 1 -d "Description..."
tk dep nw-7b89 nw-5c46  # 7b89 depends on 5c46

# Peasants check for available work
tk ready                 # List unblocked tickets

# Peasants update status as they work
tk start nw-5c46        # Mark in_progress
tk close nw-5c46        # Mark closed

# View dependencies
tk dep tree nw-5c46
```

Ticket files live in `.tickets/` with YAML frontmatter:

```
.tickets/
├── nw-3a21 - Handle refresh failures.md
├── nw-5c46 - Add refresh token storage.md
├── nw-7b89 - Implement auto-refresh logic.md
└── nw-8d12 - Add retry with backoff.md
```

## Workflow Phases

### Design

**What happens:**
- You (the King) describe what you want to build
- Hand routes to Council (3 models + synthesis)
- You iterate until satisfied
- Hand saves design and runs `kd plan` when you approve

**Artifacts:**
- `.kd/runs/<feature>/design.md`

### Plan

**What happens:**
- Hand presents design to Council
- Council generates tickets with dependencies
- Hand creates tickets via `tk create`
- Shows you the breakdown
- You can request changes
- Hand runs `kd dev` when you approve, after confirming Peasant count

**Artifacts:**
- `.tickets/*.md` - Individual ticket files

### Develop (Autopilot)

**What happens:**
- Kingdom creates worktrees for Peasants
- Hand assigns READY tickets (via `tk ready`) to idle Peasants
- Each ticket flows through the per-ticket loop with fresh agents
- Tickets auto-merge to feature branch when passing Council review + CI

**Per-ticket loop (fresh agent at each phase):**

1. **Dev (fresh agent):** Implement acceptance criteria, commit, update work log
2. **Test (fresh agent):** Write/run tests based on design + ticket + diff
3. **Review (Council):** Check diff against design + ticket, produces pass/fail
4. **Fix:** If fail, fresh dev agent addresses review comments (loops back)
5. **Merge:** When passing review + CI, auto-merges to feature branch

**Monitoring:**
- `kd status` shows ticket counts and Peasant status
- `kd attach peasant-2` to watch a specific Peasant
- `kd chat` to ask the Hand what's happening

### Merge

**What happens:**
- All tickets complete, merged to feature branch
- Hand asks if you're ready to merge to main
- You (the King) do final review
- Hand runs `kd merge` to complete

## Handling Changes Mid-Flight

**You discover a bug:**

```
You: Peasant 2 just found a bug in TokenService, unrelated to this feature.

Hand: Want me to:
1. Add a ticket to current plan (a free Peasant picks it up)
2. Handle it outside this feature (you fix it separately)
3. Pause a Peasant to fix it now (if urgent)

You: Add a ticket, low priority.

Hand: Done. Created nw-9e34 via tk, low priority. It'll get picked up
      after higher priority tickets.
```

**Design flaw discovered:**

```
You: The OAuth design is wrong - the upstream API doesn't support
     refresh token rotation like we thought.

Hand: That affects nw-7b89 and nw-3a21 which are in progress. I recommend:
1. Pause those Peasants
2. I'll route to Council for a revised approach
3. We review together, then update affected tickets

Should I pause them now?
```

## Approvals and Escalations

Even in autopilot, some things need you (the King):

1. **Dangerous operations:** Migrations, external API calls, destructive commands
2. **Blockers:** Design ambiguity, unclear requirements, failing tests

When these occur:
- Hand surfaces them in `kd status` and in chat
- You run `kd approve nw-5c46` for quick unblock
- Or `kd chat` to discuss with the Hand
- Or `kd attach ticket-nw-5c46` to talk to the Peasant directly

## File Structure

```
.tickets/
├── nw-3a21 - Handle refresh failures.md
├── nw-5c46 - Add refresh token storage.md
└── ...

.kd/
├── current                     # Pointer to active run (e.g., "oauth-refresh")
├── config.json                 # Global config (model settings, etc.)
└── runs/
    └── oauth-refresh/
        ├── state.json          # Phase, Peasant count, tmux sessions
        ├── design.md           # Design document
        ├── plan.json           # Plan metadata
        └── logs/               # Agent logs, escalations

.kd/worktrees/
├── peasant-1/                  # Git worktree for Peasant 1
├── peasant-2/                  # Git worktree for Peasant 2
└── peasant-3/                  # Git worktree for Peasant 3
```

## Tmux Server Architecture

Kingdom runs its own tmux server (`-L kd`) to avoid conflicts with your normal workflow:

```
tmux server: kd
└── session: kingdom
    ├── window: hand            # Your main interaction
    ├── window: council         # Multi-model mode (when active)
    │   ├── pane: claude
    │   ├── pane: gpt
    │   ├── pane: gemini
    │   └── pane: synthesis
    ├── window: peasant-1
    ├── window: peasant-2
    └── window: peasant-3
```

**Attaching:**
- `kd chat` → attaches to hand window
- `kd council` → attaches to council window
- `kd attach peasant-2` → attaches to that Peasant
- `kd attach ticket-nw-5c46` → attaches to Peasant handling that ticket

## Example Session

```bash
# Start a new feature
$ kd start oauth-refresh
Created branch: feature/oauth-refresh
Initialized: .kd/runs/oauth-refresh/
Started Hand in tmux server 'kd'

$ kd chat
# (attaches to Hand)

You: We need to implement OAuth token refresh. Users should stay
     logged in seamlessly.

Hand: Got it. Let me route this to the Council for design...
      [Council runs, shows 3 responses + synthesis]

      Here's the consolidated design. Ready to plan?

You: Yes, let's plan.

Hand: [Council generates tickets, Hand creates via tk]
      4 tickets, dependencies mapped. How many Peasants?

You: 3

Hand: Starting Peasants. I'll let you know when something needs you.

# Detach, do other work
# (Ctrl-B D to detach from tmux)

$ kd status
Feature: oauth-refresh  (branch: feature/oauth-refresh)
Phase: DEVELOP (autopilot, Peasants: 3)

Tickets (via tk):
  READY: 0   DOING: 2   REVIEW: 1   BLOCKED: 0   DONE: 1

Peasants:
  peasant-1: nw-7b89 (dev phase)
  peasant-2: nw-3a21 (test phase)
  peasant-3: nw-8d12 (review - Council running)

# Later
$ kd chat

Hand: nw-5c46 and nw-7b89 are merged to the feature branch. nw-3a21 is in
      Council review. nw-8d12 hit a blocker - the test environment doesn't
      have the right API keys configured.

      Want me to skip that test for now, or do you want to fix
      the environment?

You: I'll fix the environment. Give me 10 minutes.

Hand: I'll pause nw-8d12. Let me know when ready.

# After fixing
$ kd chat

You: Environment is fixed, resume nw-8d12.

Hand: Resuming. ... All tickets complete. Ready to merge to main?

You: Yes.

Hand: [runs kd merge]
      Done. feature/oauth-refresh merged to main.
```

## Open Questions

1. **Model configuration:** How do you configure which models the Council uses? `.kd/config.json`?

2. **Hand persistence:** If you close the terminal and come back, does the Hand remember the conversation? (Yes - persistent tmux session with Claude Code.)

3. **Peasant crash recovery:** If a Peasant dies mid-ticket, does the Hand detect and reassign?

4. **Multiple features:** Can you run multiple features in parallel with separate Hands? (Probably yes, with separate tmux sessions per feature.)

5. **Council timeout:** What if one Council model is slow or unresponsive?
