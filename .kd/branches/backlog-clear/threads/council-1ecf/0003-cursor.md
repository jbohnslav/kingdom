---
from: cursor
to: king
timestamp: 2026-02-14T19:18:48Z
---

Based on my review of the backlog, I recommend a **"Quality of Life & Polish"** branch. There are about 10 tickets that are high-value usability improvements or small fixes which don't require significant design work but would make the daily workflow much smoother.

Here is the suggested group of tickets to tackle in one branch:

### 1. Ticket Management Polish
*   **`115f`**: `kd tk` commands (create, close, start) should echo the ticket **title** in the output, not just the ID. This reduces cognitive load.
*   **`4789`**: `kd tk show` should accept multiple IDs or an `--all` flag to show all tickets in the current branch.
*   **`2ede`**: `kd tk create` should allow setting dependencies immediately with a `--dep` flag.

### 2. Council & Config Usability
*   **`70f6`**: `kd council show` is too verbose. It should default to showing only the **most recent turn** (last question + responses) and offer `--all` for history.
*   **`1c7b`**: `kd config show` prints noisy empty defaults (like `extra_flags: []`). It should be cleaner.

### 3. Critical Fixes
*   **`1147`**: **Bug:** `peasant --hand` mode exits immediately without doing work. This is a blocker for manual agent workflows.
*   **`083b`**: **Code Fix:** `peasant_start` shadows the `agent` parameter with a loop variable. Easy fix to prevent future bugs.
*   **`0817`**: `kd done` fails confusingly when not on a task branch; it should suggest passing the branch name as an argument.

### 4. Documentation & Help
*   **`54e3`**: `kd breakdown` currently just prints a prompt. It should guide the user to actually **create** the tickets (e.g., "Do you want to create these tickets now?").
*   **`2316`**: **Docs:** README still advertises the removed `kd breakdown --apply` command.

---

**Why this group?**
These changes are mostly "touch the CLI layer" or "small logic tweaks." They don't require deep architectural changes (unlike the Council Async UX overhaul in ticket `6412`, which I excluded as it's a bigger beast). Doing them all at once will result in a noticeably better developer experience immediately.

**Recommended Branch Name:** `polish-cli-ux`
