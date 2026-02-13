---
from: cursor
to: king
timestamp: 2026-02-13T19:27:02Z
---

The implementation of the ticket lifecycle improvements is largely correct but has one significant bug and a lack of test coverage.

### 1. Implementation Review

*   **`kd tk create`**: **Correct.** Prints the absolute file path (`str(ticket_path.resolve())`), enabling shell composition like `code $(kd tk create ...)`.
*   **`kd tk close`**: **Correct.** Automatically moves backlog tickets to `.kd/archive/backlog/tickets/` when closed.
*   **`kd tk reopen`**: **Correct.** Automatically restores archived backlog tickets to `.kd/backlog/tickets/` when reopened.
*   **`kd tk pull`**: **Correct.** Moves tickets from backlog to the current branch, with appropriate error handling if the ticket isn't in the backlog.

### 2. Bugs Found

**Bug: `kd tk start` leaves archived tickets in the archive.**

If you run `kd tk start <id>` on a closed backlog ticket (which is in the archive), the status updates to `in_progress`, but the ticket **remains in the archive**.

*   **Cause**: In `src/kingdom/cli.py`, the restore logic explicitly checks for `new_status == "open"`:
    ```python
    2183|    if new_status == "open" and ticket_path.parent.resolve() == archive_backlog_tickets.resolve():
    2184|        ticket_path = move_ticket(ticket_path, backlog_tickets)
    ```
*   **Fix**: Update line 2183 to check if `new_status` is `open` **or** `in_progress`.

### 3. Missing Tests

There appear to be **no dedicated tests** for the `kd tk` CLI commands.
*   `tests/test_ticket.py` tests the model and utility functions, not the CLI.
*   `tests/test_cli_peasant.py` tests `peasant` commands.
*   The new `kd tk pull` command and the auto-archive behaviors are currently untested.

### Recommendations

1.  **Fix the `kd tk start` bug**:
    ```python
    # In update_ticket_status
    if new_status in ("open", "in_progress") and ticket_path.parent.resolve() == archive_backlog_tickets.resolve():
        ticket_path = move_ticket(ticket_path, backlog_tickets)
    ```

2.  **Add `tests/test_cli_ticket.py`**: Create a new test file to verify these CLI behaviors, covering:
    *   `create` outputting a path.
    *   `close` moving a backlog ticket to archive.
    *   `reopen` and `start` moving an archived ticket back to backlog.
    *   `pull` moving a ticket to the current branch.
