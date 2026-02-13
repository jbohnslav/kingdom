---
from: claude
to: king
timestamp: 2026-02-13T19:20:23Z
---

Now I have a thorough understanding of the current code and the design. Here's my review.

---

## Design Review: ticket-management-ux

### Overall Assessment

The design is well-scoped and the three changes are genuinely independent. Each addresses a real friction point I can see in the code. The decisions are sound.

### Feature-by-Feature Analysis

**1. `kd tk create` prints file path (kin-7402)**

Good call. The current code at `cli.py:2007` does `typer.echo(ticket_id)` — changing this to `typer.echo(str(ticket_path))` is a one-line fix. The `vim $(kd tk create ...)` composability argument is compelling.

One thing to consider: is the output an absolute path or relative? Absolute is more robust for piping into `$EDITOR`, but relative (from repo root) is cleaner visually. I'd recommend **absolute** on stdout since it's meant for machine consumption. If a human is reading the output, they can see the ID embedded in the path anyway.

**2. Auto-archive closed backlog tickets (kin-613d)**

The design says to put the move in `update_ticket_status` since it's the "single choke point." Looking at the code (`cli.py:2157-2175`), this is correct — `ticket_close`, `ticket_start`, and `ticket_reopen` all funnel through it. The logic would be:

```
if new_status == "closed" and ticket is in backlog → move to archive/backlog/tickets/
```

Two things to watch:

- **Detection**: You need to know the ticket is in backlog. The `ticket_path` is already available at line 2171. Checking whether `"/backlog/"` is in the path string is fragile. Better: compare `ticket_path.parent` against `backlog_root(base) / "tickets"` using `Path.resolve()` or `.samefile()`.

- **Reopen edge case**: If someone runs `kd tk reopen` on an archived backlog ticket, should it move *back* to the backlog? The design doesn't mention this. I'd say yes — if you auto-archive on close, you should auto-restore on reopen. Otherwise a reopened ticket is stuck in the archive and invisible to `kd tk list --backlog`. This is the one gap I see in the design.

**3. `kd tk pull` command (kin-341e)**

Clean design. It's essentially a specialized `ticket_move` that hardcodes source=backlog, dest=current branch. Making it a separate command rather than a `--from-backlog` flag on `move` is the right call — the semantics are distinct and the name `pull` communicates intent clearly.

The error conditions are right: ticket not in backlog, or already on current branch. I'd add one more: **no active branch** (i.e., `resolve_current_run` fails). Looking at `get_tickets_dir` (`cli.py:1940-1956`), when there's no active branch it silently falls back to backlog — `pull` should error explicitly instead since pulling into the backlog makes no sense.

### On `--all`

**Recommendation: don't add `--all` yet.** Reasons:

1. **Backlog is a triage buffer, not a sprint plan.** Pulling everything defeats the purpose of having a backlog. The whole point is selective prioritization.

2. **It's trivially scriptable if needed.** A user who really wants it can do:
   ```bash
   kd tk list --backlog --json | jq -r '.[].id' | xargs kd tk pull
   ```

3. **YAGNI.** If nobody asks for it in practice, you avoided adding a footgun. If they do ask, adding it later is a non-breaking change.

4. **Risk of accidental misuse.** An agent running `kd tk pull --all` could flood a branch with 25 unrelated tickets. Explicit IDs are a natural guardrail.

If you do eventually add it, consider `--all --priority 1` (pull only P1 backlog tickets) as the more useful variant.

### Summary of Recommendations

| Item | Recommendation |
|---|---|
| Create output | Use absolute path |
| Auto-archive detection | Compare resolved paths, not string matching |
| Reopen archived backlog ticket | Auto-move back to backlog (missing from design) |
| Pull with no active branch | Error explicitly, don't fall back to backlog |
| `--all` flag | Skip for now, scriptable with `list --json \| xargs pull` |
