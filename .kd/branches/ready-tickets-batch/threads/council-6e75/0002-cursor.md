---
from: cursor
to: king
timestamp: 2026-02-14T04:40:43Z
---

Here is the implementation guidance for the 9 tickets in the `ready-tickets-batch` branch.

### **101d: Enforce read-only mode for council members**
*   **Goal:** Prevent council advisors from modifying files or running destructive commands.
*   **Key Files:** `src/kingdom/council/base.py`, `src/kingdom/agent.py`.
*   **Approach:**
    1.  **Modify `CouncilMember.COUNCIL_PREAMBLE`** in `src/kingdom/council/base.py` to explicitly forbid file modifications, deletions, and shell commands that alter state.
    2.  **Review `src/kingdom/agent.py`**: Ensure that when council members are invoked (via `kd council ask`), they are NOT given tools/permissions to write files if the backend supports tool filtering.
    3.  **Hard Constraint:** In `src/kingdom/council/base.py`, ensure `skip_permissions` is strictly `False` (it currently is, but verify no code paths override it).
*   **Gotchas:** Agents need *read* access to be useful. Ensure you don't block `read_file`, `ls`, `grep`, etc.

### **2819: Add `kd whoami` command**
*   **Goal:** Allow an agent (or user) to check their current identity/role.
*   **Key Files:** `src/kingdom/cli.py`, `src/kingdom/council/base.py`, `src/kingdom/harness.py`.
*   **Approach:**
    1.  **Implement `kd whoami`** in `src/kingdom/cli.py`. It should check environment variables like `KINGDOM_ROLE` (hand, council, peasant) and `KINGDOM_AGENT_ID`. Default to "hand" (user) if unset.
    2.  **Inject Identity:**
        *   In `src/kingdom/council/base.py` (`CouncilMember.query`), inject `KINGDOM_ROLE=council` and `KINGDOM_AGENT_ID={self.name}` into the subprocess environment.
        *   In `src/kingdom/harness.py` (`run_agent_loop`), inject `KINGDOM_ROLE=peasant` and `KINGDOM_AGENT_ID={session_name}` into the subprocess environment.
*   **Gotchas:** You must update the environment injection logic *before* the agents can use this command effectively.

### **3860: Add JSON config file for system-wide settings**
*   **Goal:** Centralize configuration (council composition, model IDs, etc.).
*   **Key Files:** `src/kingdom/state.py`, `src/kingdom/council/council.py`.
*   **Approach:**
    1.  **Define Config Path:** Use `.kd/config.json` (or `config.toml`).
    2.  **Load Config:** Add a `load_config` function in `src/kingdom/state.py`.
    3.  **Apply Config:** Update `Council.create` in `src/kingdom/council/council.py` to read this config and override default agent settings (e.g., swapping `claude` model or timeout).
*   **Gotchas:** Ensure backward compatibility if the config file is missing (fall back to defaults).

### **8af5: `kd done` should error if branch has open tickets**
*   **Goal:** Prevent closing a session with unfinished work.
*   **Key Files:** `src/kingdom/cli.py`.
*   **Approach:**
    1.  **Modify `done` command:** Before marking status as "done", call `list_tickets` for the current branch.
    2.  **Check Status:** Iterate through tickets; if any are `open` or `in_progress`, print them and raise `typer.Exit(1)`.
    3.  **Add Override:** Add a `--force` flag to bypass this check.
*   **Gotchas:** Only check tickets belonging to the *current branch*, not the backlog.

### **98f3: `kd tk move` should remove source file**
*   **Goal:** Fix issue where moved tickets leave a ghost copy behind.
*   **Key Files:** `src/kingdom/ticket.py` (`move_ticket`).
*   **Approach:**
    1.  **Verify `move_ticket`:** It currently uses `path.rename()`. While this *should* move the file, it might behave unexpectedly across filesystems or with git.
    2.  **Robust Move:** Change implementation to use `shutil.move` for safety, or better yet, use `git mv` if inside a git repo (to preserve history and ensure git index is updated).
    3.  **Explicit Cleanup:** If not using `git mv`, ensure the source file is definitely unlinked after the copy.
*   **Gotchas:** If the source file is tracked by git and you just `os.rename` it, git sees a deletion and a new file. `git mv` is preferred.

### **98fe: `kd start` should populate `design.md`**
*   **Goal:** Auto-create design doc template on session start.
*   **Key Files:** `src/kingdom/cli.py`.
*   **Approach:**
    1.  **Update `start` command:** Import `build_design_template` from `kingdom.design`.
    2.  **Populate:** After creating the branch layout, check if `design.md` exists. If not, write the template content to it.
    3.  **Feedback:** Print "Created design template at ..." so the user knows.

### **b5aa: Enable branch protection on master**
*   **Goal:** Protect the `master`/`main` branch.
*   **Key Files:** N/A (GitHub Configuration).
*   **Approach:**
    *   This is not a code change. You (or the King) must run this via `gh` CLI or the GitHub UI.
    *   *Recommendation:* Create a script `scripts/protect_branch.sh` using `gh api` to enforce this, or just mark the ticket as a manual task.

### **c5cb: Replace `kd breakdown` logic with agent prompt output**
*   **Goal:** Simplify `breakdown` by offloading logic to the agent.
*   **Key Files:** `src/kingdom/cli.py`, `src/kingdom/breakdown.py`.
*   **Approach:**
    1.  **Simplify `breakdown` command:** Remove the `--apply` flag and the complex parsing logic.
    2.  **New Output:** The command should simply print a prompt: "Read `design.md`. Create tickets using `kd tk create`. Link dependencies using `kd tk dep`."
    3.  **Cleanup:** Delete `parse_breakdown_tickets` and related "two-pass" logic from `src/kingdom/breakdown.py`.
*   **Gotchas:** This is a destructive refactor. Ensure you don't break the ability to generate the initial `breakdown.md` template.

### **e4b1: Add `kd status` command showing agent workload**
*   **Goal:** Visibility into what agents are doing.
*   **Key Files:** `src/kingdom/cli.py`.
*   **Approach:**
    1.  **Resolve Conflict:** `kd status` already exists (shows branch status). You can either:
        *   Enhance existing `status` to include agent info.
        *   Create `kd agent-status` (or `kd workload`).
    2.  **Implementation:** Use `list_active_agents` (from `session.py`) to find running agents.
    3.  **Integration:** Use the logic from `peasant_status` but expand it to include council members if applicable, or just expose `peasant_status` as a top-level command.
*   **Dependencies:** Depends on **2819** (`whoami`) logic if you want to highlight "my" assignments.

### **Suggested Order**
1.  **2819 (`whoami`)**: Foundation for identity.
2.  **e4b1 (`status`)**: Depends on identity.
3.  **101d (Read-only)** & **b5aa (Branch protection)**: Security/Safety first.
4.  **98f3 (Move fix)** & **8af5 (Done check)**: Fix workflow bugs.
5.  **98fe (Start)** & **c5cb (Breakdown)**: Improve the "Start" phase workflow.
6.  **3860 (Config)**: Can be done anytime, but might require refactoring other parts.
