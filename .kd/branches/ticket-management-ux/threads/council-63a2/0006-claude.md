---
from: claude
to: king
timestamp: 2026-02-13T19:26:52Z
---

Good, now I have the full picture. Here's my review.

---

## Implementation Review

### 1. `kd tk create` — prints absolute path (kin-7402)

**`cli.py:2007`**: `typer.echo(str(ticket_path.resolve()))` — Correct.

**`cli.py:1974`**: `sys.stderr.write(...)` for the priority clamping warning — Correct, `sys` is imported at line 15.

**No issues here.** Clean, minimal change.

---

### 2. Auto-archive/restore on close/reopen (kin-613d)

**`cli.py:2175-2183`** — This is where I have findings.

**Bug: write-then-move writes to stale path.** Lines 2174-2178:

```python
write_ticket(ticket, ticket_path)              # writes to backlog/tickets/kin-XXXX.md

if new_status == "closed" and ticket_path.parent.resolve() == backlog_tickets.resolve():
    ticket_path = move_ticket(ticket_path, archive_backlog_tickets)
```

This works, but it's doing an unnecessary write-then-rename. `write_ticket` writes the updated status to the backlog location, then `move_ticket` renames the file to the archive location. Functionally correct since `move_ticket` uses `Path.rename()` which is atomic on the same filesystem. **Not a bug, just a minor inefficiency.** The alternative (move then write) would be worse — if the write fails after the move, you'd have a ticket in the archive with the wrong status.

**Potential issue: archive path detection on reopen.** Lines 2181-2183:

```python
if new_status == "open" and ticket_path.parent.resolve() == archive_backlog_tickets.resolve():
    ticket_path = move_ticket(ticket_path, backlog_tickets)
```

The `ticket_path` used here is the *original* path from `find_ticket`. For the reopen case, `find_ticket` searches the archive (confirmed at `ticket.py:328-334`), so the path will correctly point to `archive/backlog/tickets/`. This is fine.

**But wait** — there's a subtle ordering issue. On **close**, the first `if` fires and reassigns `ticket_path`. Then the second `if` checks the *new* `ticket_path` (now in archive). If `new_status == "closed"`, the second `if` tests `new_status == "open"`, which is false, so no double-move. **Safe.**

On **reopen**, the first `if` tests `new_status == "closed"`, which is false. The second `if` correctly fires. **Safe.**

**Edge case: closing a ticket that's already in `archive/backlog/tickets/`.** If someone runs `kd tk close` on a ticket that's already closed and archived (e.g., running `close` twice), the first `if` checks the original path against `backlog_tickets` — but the ticket is in `archive/backlog/tickets/`, not `backlog/tickets/`, so the condition is false. No move happens. The status gets written to the archive location. **Correct behavior, no double-move.**

**Edge case: reopening a backlog ticket that was never archived.** If an old ticket in `backlog/tickets/` has status `closed` (from before this feature), `kd tk reopen` checks the second condition: `ticket_path.parent.resolve() == archive_backlog_tickets.resolve()`. The ticket is in `backlog/tickets/`, not `archive/backlog/tickets/`, so the condition is false. It just reopens in place. **Correct — no accidental move.**

**No bugs found in this feature.**

---

### 3. `kd tk pull` command (kin-341e)

**`cli.py:2312-2352`** — Two issues.

**Issue 1: `find_ticket` is unscoped — searches everywhere, not just backlog.**

```python
result = find_ticket(base, tid)
```

`find_ticket` without a `branch` argument searches all branches, backlog, *and archive*. This means `kd tk pull a1b2` will find a ticket on another branch or in the archive, then fail at the "is not in the backlog" check. That works but gives a confusing error message: `"Error: kin-a1b2 is not in the backlog"` when the user may not realize the ticket is on another branch.

This isn't a bug per se — the validation catches it — but passing `branch=feature` would scope the search to the current branch + backlog, which would miss archive tickets. Actually, that's also wrong because you'd miss backlog tickets if the branch param scopes differently... Let me re-read `find_ticket`:

```python
if branch:
    # Scoped search: only current branch + backlog
```

So `branch=feature` would search the current branch + backlog, which is actually the right scope for `pull`. But you'd lose the ability to find the ticket in archives for a better error message. **Current approach is fine — unscoped search + explicit backlog check is the safer pattern.** The error message could be more helpful (e.g., telling the user where the ticket actually is), but that's polish, not a bug.

**Issue 2 (actual bug): partial move on multi-ID pull.** The design says "fail-fast on first error," and the code does exit on the first validation error. But the loop **moves tickets as it validates**:

```python
for tid in ticket_ids:
    # ... find ticket ...
    # ... validate in backlog ...
    new_path = move_ticket(ticket_path, dest_dir)   # <-- MOVE HAPPENS HERE
    typer.echo(str(new_path.resolve()))
```

If you run `kd tk pull aaa bbb ccc` and `bbb` fails validation, `aaa` has already been moved but `ccc` hasn't. You're left in a partial state. The design says "validate before moving, stop on first error" — but the implementation validates *and* moves in the same loop.

**Fix:** Two-pass approach. First loop validates all tickets (collecting them), second loop moves them. Something like:

```python
# Pass 1: validate all
validated = []
for tid in ticket_ids:
    result = find_ticket(base, tid)
    ...  # error checks
    if ticket_path.parent.resolve() != backlog_tickets.resolve():
        ... error ...
    validated.append((ticket, ticket_path))

# Pass 2: move all
for ticket, ticket_path in validated:
    new_path = move_ticket(ticket_path, dest_dir)
    typer.echo(str(new_path.resolve()))
```

---

### 4. Missing Tests

The test diff is empty — **no tests were added for any of the three features**. The existing `test_ticket.py` covers the data model and utility functions but has zero CLI-level tests. Here's what's needed:

| Feature | Test needed |
|---|---|
| **create prints path** | Assert stdout contains an absolute path ending in `.md`, not a bare `kin-XXXX` ID |
| **create stderr warning** | Assert priority clamping warning goes to stderr, not stdout |
| **close archives backlog ticket** | Create ticket in backlog, close it, assert file moved to `archive/backlog/tickets/` |
| **close branch ticket stays put** | Create ticket on branch, close it, assert file remains in branch |
| **reopen restores archived backlog** | Archive a closed backlog ticket, reopen it, assert file moved back to `backlog/tickets/` |
| **reopen non-archived backlog** | Close a backlog ticket (legacy, pre-archive), reopen it, assert it stays in `backlog/` |
| **pull single ticket** | Pull a backlog ticket, assert it lands in branch's `tickets/` dir |
| **pull multiple tickets** | Pull 2-3 tickets, assert all moved |
| **pull non-backlog errors** | Try to pull a branch ticket, assert error and exit code 1 |
| **pull no active run errors** | Run pull with no `kd start`, assert error |
| **pull not-found errors** | Pull a nonexistent ID, assert error |

---

### Summary

| Severity | Finding |
|---|---|
| **Bug** | `ticket_pull` does validate-and-move in one pass — partial moves on multi-ID failure. Design specifies two-pass. |
| **Missing** | No tests added for any of the three features. |
| **Cosmetic** | `ticket_pull` error message for non-backlog tickets could say where the ticket actually is. |
| **Clean** | `ticket_create` path change and `update_ticket_status` archive/restore logic are both correct. |

The archive/restore logic in `update_ticket_status` is well done — I tested every combination mentally and found no edge case bugs. The two-pass fix for `ticket_pull` is straightforward.
