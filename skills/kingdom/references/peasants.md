# Peasant Workers and Worktrees

Peasants are unattended agent workers that execute tickets. Worktree mode gives
them isolated parallel state; hand mode runs serially in the current checkout.
For bounded research, review, or implementation slices within the current host
session, prefer native subagents and keep the owning session responsible for
integrating their results.

## Launching

```bash
# Worktree mode (default): creates .kd/worktrees/<id>/, runs in isolation
kd peasant start <ticket-id>

# Hand mode: runs in current directory, serial execution
kd peasant start <ticket-id> --hand

# Specify which agent to use (default: claude)
kd peasant start <ticket-id> --agent codex
```

## Managing Active Peasants

```bash
kd peasant status            # show all active peasants
kd peasant watch <id>        # live-follow a peasant's progress
kd peasant show <id>         # view structured peasant history
kd peasant stop <id>         # stop a running peasant
```

## Communication

```bash
kd peasant msg <id> "Focus on the API layer first"    # send directive
kd peasant read <id>                                   # read messages from peasant
```

## Worktree Lifecycle

```bash
kd peasant sync <id>         # pull parent branch changes into worktree
kd peasant review <id>       # review completed work
kd peasant clean <id>        # remove worktree when done
```

## When to Use Peasants

- **Worktree mode** for well-scoped tickets that benefit from unattended,
  isolated implementation and durable review
- **Hand mode** for serial peasant execution that needs the full checkout context
- **Native subagents instead** for bounded host-local delegation where the owning
  session should coordinate and integrate the result directly
- **Lord mode instead** when an epic needs autonomous scheduling and integration
  across multiple peasant tickets

## Reviewing Peasant Work

Peasants proceed to council review by default. Keep that default unless the King
explicitly chooses otherwise. When the peasant and council finish, the owning
session still reviews the combined evidence and accepts or rejects:

```bash
kd peasant review <id>       # review completed work (shows diff + worklog)
kd peasant accept <id>       # accept work and close the ticket
kd peasant reject <id>       # reject with feedback — peasant iterates
```

Council approval is an input to the owning session's review, not an automatic
merge decision. Confirm integration fit, ticket evidence, acceptance criteria,
and tests before acceptance.

## Recovery

- Start fails because the ticket is `in_review` or closed: inspect the ticket and
  resolve or reopen its current lifecycle state before retrying.
- Peasant seems stuck: inspect `kd peasant status` and `kd peasant show <id>`;
  send a targeted message or stop it only after reading its state.
- Council review is still active: `kd peasant watch <id>` shows the peasant and
  council progression. Do not launch duplicate work.
- Accept refuses a dirty parent checkout: commit or stash intended parent changes
  before accepting.

### Merge conflict recovery

If `kd peasant accept <id>` produces merge conflicts, the merge is already in
progress on the feature branch:

1. Resolve each conflict in the feature-branch checkout.
2. Stage the resolved files and commit to complete the merge.
3. Run `kd peasant accept <id>` again.

Accept is idempotent after the ticket branch is merged: the second call skips the
merge and finishes ticket closure and cleanup. Never discard the feature branch
or unrelated working-tree changes to escape the conflict.
