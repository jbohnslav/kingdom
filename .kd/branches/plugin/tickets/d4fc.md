---
id: "d4fc"
status: in_progress
deps: []
links: []
created: 2026-02-27T13:24:39Z
type: task
priority: 1
---
# Claude Code plugin for kingdom workflow

Merged from d4fc (auto-worklog) and bdfc (reminders after turns). Core intent: a Claude Code hooks plugin that helps agents follow the kingdom workflow automatically.

## Problem

Work logs should be a running narrative of what happened — "user asked X, I investigated Y, found Z." But right now you have to manually prompt the agent to update the work log every time. It should be automatic.

Similarly, agents need periodic reminders about kd workflow (update worklogs, commit .kd/ changes, check ticket status) — a post-turn hook can inject these.

Claude Code supports hooks that fire on events like `stop` (after every assistant turn before waiting for user input). A kingdom hooks plugin could handle both concerns.

## Research: Claude Code Hooks System

### Hook events relevant to us

| Event | When | Key data | Use for |
|-------|------|----------|---------|
| `Stop` | Claude finishes responding | `stop_hook_active`, `last_assistant_message` | Auto-worklog summary, workflow reminders |
| `PostToolUse` | After any tool succeeds | `tool_name`, `tool_input`, `tool_response` | Track file edits, test runs, commands |
| `SessionStart` | Session begins/resumes | `source`, `model` | Inject ticket context at session start |
| `SubagentStop` | Subagent finishes | `agent_id`, `agent_type`, `last_assistant_message` | Track peasant activity |
| `PreCompact` | Before context compaction | `trigger`, `custom_instructions` | Re-inject ticket context after compaction |

### Hook handler types

- **`command`**: Shell script, receives JSON on stdin, outputs JSON/text to stdout. Most common. Can be `async: true` for background work.
- **`prompt`**: Sends event data to a Claude model (Haiku by default) for single-turn evaluation. Returns `{ok: true/false, reason: "..."}`. Good for semantic decisions (e.g. "was this turn meaningful?").
- **`agent`**: Spawns a subagent with tool access (Read, Grep, etc.) for up to 50 turns. 60s default timeout.
- **`http`**: POSTs event JSON to a URL. Good for team-shared audit services.

### How to inject context back

Hooks can inject text into Claude's context via:
1. **Plain stdout** (exit 0) — added to Claude's context as hook output
2. **JSON `additionalContext`** (preferred) — structured injection:
   ```json
   {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "Reminder: ..."}}
   ```
3. **`systemMessage`** — shown to user as a warning banner (not to Claude)

### Infinite loop prevention

`Stop` hooks receive `stop_hook_active: true` when Claude is already continuing from a previous stop hook. **Must check this to prevent infinite loops.** If `stop_hook_active` is true, exit 0 with no output.

### Configuration

```json
// .claude/settings.json (project-level, committable)
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/kd-workflow.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Can also be defined in **skill frontmatter** — scoped to skill lifetime and cleaned up when it finishes. This is powerful for kingdom: the skill installs its own hooks when active.

### Key ecosystem lessons

1. **Hooks > CLAUDE.md for enforcement.** If you need something to actually happen, a hook is the only reliable mechanism. CLAUDE.md is aspirational; hooks are deterministic.
2. **`PostToolUse` on `Edit|Write` is the workhorse** for auto-formatting, linting, quality checks.
3. **Prompt hooks** (`type: "prompt"`) are ideal for "was this meaningful?" decisions — let Haiku decide if a turn warrants a worklog entry.
4. **Skills should install their own hooks** via frontmatter rather than relying on global settings.
5. **Keep hooks fast** — they block the agentic loop. 5-10s timeout max for synchronous hooks.
6. **Community pain point**: no sequential/conditional hooks (run in parallel). Conditions must be coded inside the script.

### Notable community examples

- **[disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery)**: 13 hooks, UV single-file Python scripts. Good architecture reference.
- **[tfriedel/claude-worktree-hooks](https://github.com/tfriedel/claude-worktree-hooks)**: WorktreeCreate/Remove hooks — copy .env, install deps, assign ports.
- **[rinadelph/rins_hooks](https://github.com/rinadelph/rins_hooks)**: Auto-commit every file change with contextual messages.
- **[mattbrailsford.dev](https://mattbrailsford.dev/replacing-my-custom-git-worktree-skill-with-claude-code-hooks)**: Replaced 760 lines of custom skill code with native worktree hooks.

## Design

### Guiding Principle

**Minimalist plugin, maximalist skill.** The plugin is a thin enforcement layer — it reminds agents to do things the skill already teaches. All workflow knowledge, judgment, and state lives in the skill and `kd` CLI respectively. The plugin never duplicates what the skill covers; it nudges agents to actually follow through.

### Architecture

**Single `Stop` command hook** that fires after every agent turn. No LLM calls, no async background work — just fast context detection and targeted reminders injected via `additionalContext`.

```
Stop → kd-workflow.sh → detect context → inject relevant reminders → exit 0
```

The hook asks: "Given what just happened, does the agent need a nudge to follow the workflow?" Examples of nudges:

- **King weighed in on a decision?** → "Update the ticket with this decision."
- **Did research or investigation?** → "Log your findings in the ticket worklog, not just in chat."
- **King suggested a new feature or improvement?** → "Create a backlog ticket with `kd tk create --backlog`."
- **Made meaningful progress?** → "Update the worklog with what you did and learned."
- **About to close a ticket?** → "Check acceptance criteria first."
- **Ticket status may need changing?** → "Do you need to start, close, or update a ticket?"

The hook is NOT responsible for:
- Tracking dirty `.kd/` files (many projects gitignore `.kd/`)
- Auto-generating worklog entries (that's the agent's job, the hook just reminds)
- Workflow policy decisions (that's the skill's domain)
- Cross-branch or session logic (that's `kd`'s domain)

### Context Detection

The hook uses `kd` as its source of truth — no direct `.kd/` file crawling.

```bash
# Get current context from kd (stable machine interface)
CONTEXT=$(kd hook context --json 2>/dev/null) || exit 0
```

This means we need a `kd hook context` command that outputs:
- Active session/branch
- Current ticket (id, title, status, acceptance criteria)
- Whether there's an active ticket at all

### Skip Conditions

- `stop_hook_active` is true → exit 0 (infinite loop prevention)
- No active kd session → exit 0
- No active ticket → still remind about ticket creation if relevant

### Installation

**Option C: `kd` manages hook installation.** Opt-in first:

```
kd plugin enable    # writes hooks to .claude/settings.json
kd plugin disable   # removes them
```

Not auto-installed by `kd start` yet. Hooks are behavioral and can annoy if unstable. Once proven, we can have `kd start` offer to enable them.

### What stays in the skill

Everything about *how* to work: ticket-first reflex, council consultation patterns, close-out hygiene, worklog writing style, when to break down tickets, how to handle design phases. The skill teaches; the hook reminds.

## Acceptance Criteria

- [ ] Single `Stop` command hook fires after each agent turn
- [ ] Hook calls `kd hook context --json` for context (no direct .kd/ crawling)
- [ ] Contextual workflow reminders injected via `additionalContext` (worklog updates, ticket status changes, backlog creation, AC checks)
- [ ] Infinite loop prevention (`stop_hook_active` check)
- [ ] `kd hook context --json` command exists and returns session/ticket info
- [ ] `kd plugin enable` installs hooks to `.claude/settings.json`
- [ ] `kd plugin disable` removes hooks
- [ ] Hook script is fast (<2s) with no LLM calls

## Worklog

- 2026-03-04 13:51 — Deep dive on Claude Code hooks system complete. Key findings:

  - 17 hook events available. Stop is our primary target (fires after every Claude response).
  - 4 handler types: command (shell), prompt (Haiku eval), agent (multi-turn), http (webhook).
  - Hooks inject context via additionalContext JSON field or plain stdout.
  - Must check stop_hook_active to prevent infinite loops.
  - Prompt hooks are ideal for 'was this meaningful?' decisions but can't call kd tk log directly.
  - Community lesson: hooks > CLAUDE.md for enforcement. Skills can install their own hooks via frontmatter.

  Design written up with three architecture options: command hook for reminders, prompt/agent hook for auto-worklog, and open questions about aggressiveness and installation method.

  Ticket updated with full research + design. Ready for King review.
- 2026-03-04 14:05 — Council discussion on plugin architecture. King decided: minimalist plugin, maximalist skill. Single Stop command hook with contextual reminders (no LLM calls, no async). Focus on nudging agents to follow the workflow — update tickets on decisions, log findings to worklogs not just chat, create backlog tickets when king suggests features. No dirty .kd/ tracking (many projects gitignore it). Installation via kd plugin enable/disable (Option C, codex's suggestion). Hook uses kd hook context --json for state (no direct file crawling). Ticket updated with resolved design, cleaned up open questions, revised AC.
