---
from: claude
to: king
timestamp: 2026-02-13T14:12:45Z
---

Here's the full review against the design doc.

---

## Design Doc vs Current Code: Line-by-Line Review

### Requirement 1: `kd work <ticket>` — **Done, all sub-items addressed**

| Sub-item | Status | Evidence |
|---|---|---|
| Runs autonomous loop for ticket | **Pass** | `cli.py:1700` calls `run_agent_loop()` |
| Uses cwd as workspace | **Pass** | Interactive mode: `worktree or str(Path.cwd())` at line 1682 |
| Foreground or background | **Pass** | Top-level `@app.command("work")`, no daemon logic — foreground by default, `peasant start` wraps it via Popen |
| Updates session state | **Pass** | Harness calls `update_agent_state` throughout the loop |
| Seeds thread with ticket content | **Pass** | Lines 1689-1696 seed the thread identically to `peasant_start` |
| Honors `--base` flag | **Pass** | `_resolve_peasant_context(ticket_id, base=base)` at line 1678; `_resolve_peasant_context` accepts `base: Path | None = None`, defaults to `Path.cwd()` at line 979 |

### Requirement 2: Refactor `kd peasant start` — **Done**

| Sub-item | Status | Evidence |
|---|---|---|
| Invokes `kd work` (not `kingdom.harness` or `kd agent run`) | **Pass** | `launch_work_background` builds `python -m kingdom.cli work ...` (line 1028-1033) |
| Parallel: worktree → `kd work` in background | **Pass** | `peasant_start` creates worktree (line 1097), passes `worktree_path` to helper (line 1119) |
| Hand: `kd work` in cwd, background | **Pass** | `--hand` flag (line 1066), sets `worktree_path = base` (line 1093), same `launch_work_background` call |

### Requirement 3: Extract `launch_work_background` helper — **Done**

| Sub-item | Status | Evidence |
|---|---|---|
| Shared helper, not duplicated inline | **Pass** | `launch_work_background` at line 1008, called from `peasant_start` (line 1119) and `peasant_review` (line 1550) |

### Requirement 4: Clean up dead code — **Done**

| Sub-item | Status | Evidence |
|---|---|---|
| Remove `harness.py:main()` and `__main__` | **Pass** | File ends at line 447 (`return final_status`), no `main()` or `__main__` block |
| Remove empty `agent_app` typer group | **Pass** | `grep agent_app` returns no matches |

### Env var stripping (from council review, not in original requirements) — **Done correctly**

| Site | Stripped? | How |
|---|---|---|
| `harness.py:334` (leaf — calls `claude --print`) | **Yes** | `env=clean_agent_env()` |
| `council/base.py:75` (leaf — calls `claude --print`) | **Yes** | `env=clean_agent_env()` |
| `launch_work_background` (intermediate — spawns Python) | **No** (correct) | No `env` kwarg — doesn't need it, leaf handles it |
| Council worker Popen (intermediate — spawns Python) | **No** (correct) | No `env` kwarg — same reasoning |
| `clean_agent_env()` centralized in `agent.py:320` | **Yes** | Single definition, imported by both leaf sites |

### Tests — **All passing**

436 passed, 3 skipped, 0 failures. The previously broken tests mocking `launch_harness` have been fixed.

### Issues from the "Issues Found" section of the design doc

| Issue | Status |
|---|---|
| 1. Test failures | **Fixed** — 436 pass |
| 2. `kd work` ignores `--base` | **Fixed** — `_resolve_peasant_context` now accepts `base` param |
| 3. Duplicated Popen boilerplate | **Fixed** — `launch_work_background` helper |
| 4. No thread seed in interactive `kd work` | **Fixed** — lines 1689-1696 |
| 5. Dead code | **Fixed** — `harness.py:main()` and `agent_app` removed |

---

**Verdict: the code matches the design doc on all requirements and all identified issues are resolved.** Tests are green. The implementation is clean — `kd work` is the atomic primitive, `peasant start` is the orchestrator, env stripping is centralized at the leaf call sites, and the dead code is gone.
