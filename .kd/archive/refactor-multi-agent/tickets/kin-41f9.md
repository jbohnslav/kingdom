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

## Worklog

- Launched peasant on kin-b202 as the smoke test ticket. Peasant blocked on file write permissions (no auto-approve for edits).
- `kd peasant read` shows good messages — the agent wrote those itself and they're informative. But `kd peasant logs --follow` just to snoop on what the agent is doing is not working — only shows iteration boundaries and final status, no visibility into what the agent is actually doing.
- The agent doesn't have file write permissions, which is crazy — it's blocked on editing a file in its own worktree. Peasants need to be launched with write permissions enabled.
- `kd peasant status` works.
- No `kd peasant restart` command. `kd peasant start` again works (reuses existing worktree, relaunches harness) but it's not obvious.
- Peasant looped 8 iterations saying DONE but harness kept overriding to CONTINUE because tests failed. The failing test was `test_agent.py` — our kin-8093 permissions fix changed the expected command output, but the worktree was created from an older commit and doesn't have the updated tests. Worktrees get stale and don't pick up parent branch changes.
- Harness doesn't log which tests failed or the test output — just "Tests failed, overriding DONE to CONTINUE". Impossible to debug from logs alone.
- Worktree editable install points to the main repo, not the worktree. Peasant needs to `uv sync` in the worktree before running tests, otherwise `python -m pytest` picks up old code from the main checkout. The peasant actually got confused and ran `uv pip install -e .` manually instead, which is wrong. Harness prompt should tell peasants about this.
- Pre-commit hooks not running in the worktree — peasant committed code with unsorted imports that ruff caught during `kd peasant review`. Either `pre-commit install` wasn't run in the worktree or hooks were bypassed. Harness should ensure pre-commit is set up in new worktrees.
- `kd peasant review --reject` sends feedback to the thread but doesn't relaunch the harness. Peasant shows as "dead" (session says working but PID is gone). Have to manually `kd peasant start` again after reject.
- Rejected with "run ruff check and ruff format", restarted peasant twice. Both times it said DONE in 1 iteration and tests passed, but the ruff issue was never fixed — harness only runs pytest, not ruff/pre-commit, so the quality gate is incomplete.
- Messages sent via `kd peasant msg` while the harness is not running are lost — they go to the thread but the harness only reads them on the next iteration, which never happens if it already exited.
- The harness test runner (`run_tests` in harness.py) is the only quality gate. It doesn't run ruff or pre-commit. But `kd peasant review` runs both pytest and ruff. So review catches things the harness doesn't — mismatch between what the harness validates and what review checks.
- Fixed ruff issues manually, merged `ticket/kin-b202` into `refactor/multi-agent` (fast-forward).
- `kd peasant clean` works.
- Council agents have the same elevated skip-permissions flags as peasants (`--dangerously-skip-permissions`, etc.). During `kd council ask`, cursor actually edited design.md instead of just proposing changes. Council queries are read-only — agents should run without skip-permissions flags. `build_command()` in agent.py needs a parameter to control whether permissions are elevated (peasants: yes, council: no).
