---
id: kin-41f9
status: open
deps: []
links: []
created: 2026-02-08T17:50:21Z
type: task
priority: 1
---
# End-to-end peasant orchestration smoke test

Manually test the full peasant lifecycle by using the system to complete a real (small) ticket. No design doc needed — just a ticket for the peasant to work on and the orchestration commands.

## Setup

Create a small, self-contained ticket for the peasant to solve. Something that touches 1-2 files and has clear acceptance criteria. Examples:
- Add a `--json` flag to `kd tk show` that outputs raw frontmatter as JSON
- Add a `kd peasant clean --all` variant that removes all worktrees
- Any small bug or enhancement you've been meaning to do

```bash
kd tk create "your small task title" -p 3
# note the ticket ID, e.g. kin-XXXX
```

## Orchestration — the commands

### 1. Launch the peasant

```bash
kd peasant start <ticket-id> --agent claude
```

This creates a worktree, work thread, session, and launches the harness in the background. You should see output confirming the PID, worktree path, and thread ID.

### 2. Monitor

```bash
kd peasant status          # table of active peasants
kd peasant logs <ticket-id> --follow   # tail the subprocess output live
```

`status` shows the peasant's state (working/blocked/done/dead) and elapsed time. `logs --follow` shows the raw harness output as it calls the backend.

### 3. Interact (if needed)

If the peasant gets blocked or you want to steer it:

```bash
kd peasant read <ticket-id>                        # see what the peasant said
kd peasant msg <ticket-id> "use JWT, not opaque"   # send a directive
```

Directives are picked up on the peasant's next loop iteration.

### 4. Review

Once the peasant signals done (check `kd peasant status`):

```bash
kd peasant review <ticket-id>    # runs pytest + ruff, shows diff + worklog
```

Look at the quality gate results, the diff, and the worklog. Then either:

```bash
kd peasant review <ticket-id> --accept              # close ticket, mark done
kd peasant review <ticket-id> --reject "fix X"      # send feedback, peasant resumes
```

### 5. Cleanup

After accepting:

```bash
kd peasant clean <ticket-id>     # remove the worktree
```

The ticket branch (`ticket/<ticket-id>`) remains for merging.

## What to watch for

- Does `kd peasant start` actually launch the agent and produce logs?
- Does the harness loop iterate (check logs for "=== Iteration N ===")?
- Does the agent commit in the worktree? (`git -C .kd/worktrees/<ticket-id> log --oneline`)
- Does `kd peasant msg` actually influence the agent's next iteration?
- Does `kd peasant review` produce useful output for making an accept/reject decision?
- Any crashes, hangs, or surprising behavior?

## Acceptance

- [ ] Peasant started and harness loop ran at least one iteration
- [ ] `kd peasant status` showed the running peasant
- [ ] `kd peasant read` showed peasant messages
- [ ] `kd peasant review` ran quality gates and showed diff + worklog
- [ ] Ticket accepted or rejected via review
- [ ] Notes on what broke or felt wrong captured in worklog below
