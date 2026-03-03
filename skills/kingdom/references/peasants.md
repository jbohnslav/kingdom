# Peasant Workers and Worktrees

Peasants are agent workers that execute ticket work. They can run in isolated git worktrees (parallel) or in the current directory (serial).

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
kd peasant logs <id>         # view peasant output
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

- **Worktree mode** for tickets that can run in parallel without conflicting
- **Hand mode** for sequential work that needs the full repo context
- **Multiple peasants** can run simultaneously on different tickets in worktree mode

## Reviewing Peasant Work

When a peasant finishes its ticket, review and accept or reject:

```bash
kd peasant review <id>       # review completed work (shows diff + worklog)
kd peasant accept <id>       # accept work and close the ticket
kd peasant reject <id>       # reject with feedback — peasant iterates
```
