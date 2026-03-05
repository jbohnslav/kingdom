#!/usr/bin/env bash
# Kingdom workflow hooks for Claude Code.
# Handles: SessionStart (behavioral brief), UserPromptSubmit (per-turn reminder),
# PostToolUse (state tracking), Stop (blocker).
set -euo pipefail

# Read the hook event JSON from stdin.
input=$(cat)

# Bypass all blocking if requested.
if [ "${KD_HOOK_BYPASS:-}" = "1" ]; then
    exit 0
fi

event=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hook_event_name', ''))" 2>/dev/null || echo "")

if [ "$event" = "SessionStart" ]; then
    cat <<'EOF'
KINGDOM WORKFLOW: You are working in a project managed by the kd CLI. Before coding or research, ensure work is tracked with a ticket.
 1. TICKET FIRST — King says something? Ask yourself: does this need a ticket? Bug, idea, complaint, scope change → kd tk create immediately.
 2. LOG PROACTIVELY — Decision made, root cause found, scope changed, work completed → kd tk log. The King should never have to ask.
 3. MOVE vs CREATE — Work belongs elsewhere → kd tk move. New problem noticed → kd tk create --backlog.
EOF
    exit 0
fi

if [ "$event" = "UserPromptSubmit" ]; then
    cat <<'EOF'
Kingdom: create or update a ticket? (kd tk create|move|log). King decision? Log it. Finished work item? Log it. Found a bug? Ticket it.
EOF
    # Reset turn state and clean up stale files.
    echo "$input" | python3 -c "
import sys, json, os, time, pathlib

data = json.load(sys.stdin)
sid = data.get('session_id', '')
if not sid:
    sys.exit(0)

runtime = pathlib.Path(os.environ.get('CLAUDE_PROJECT_DIR', '.')) / '.kd' / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)

# Reset turn state for this session.
state_file = runtime / f'turn-{sid}.json'
state_file.write_text(json.dumps({'had_work': False, 'did_log': False}))

# TTL cleanup: remove turn state files older than 24h.
cutoff = time.time() - 86400
for f in runtime.glob('turn-*.json'):
    try:
        if f.stat().st_mtime < cutoff:
            f.unlink()
    except OSError:
        pass
" 2>/dev/null || true
    exit 0
fi

# Stateful hooks: PostToolUse and Stop.
if [ "$event" = "PostToolUse" ] || [ "$event" = "Stop" ]; then
    echo "$input" | python3 -c "
import sys, json, os, pathlib

data = json.load(sys.stdin)
event = data.get('hook_event_name', '')
sid = data.get('session_id', '')
runtime = pathlib.Path(os.environ.get('CLAUDE_PROJECT_DIR', '.')) / '.kd' / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)

if not sid:
    sys.exit(0)

state_file = runtime / f'turn-{sid}.json'

if event == 'PostToolUse':
    # Read current state (fail-open).
    try:
        state = json.loads(state_file.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        sys.exit(0)

    tool = data.get('tool_name', '')
    work_tools = {'WebSearch', 'WebFetch', 'Edit', 'Write'}

    if tool in work_tools:
        state['had_work'] = True

    if tool == 'Bash':
        cmd = data.get('tool_input', {}).get('command', '')
        if 'kd tk log' in cmd or 'kd ticket log' in cmd:
            state['did_log'] = True

    state_file.write_text(json.dumps(state))

elif event == 'Stop':
    stop_active = data.get('stop_hook_active', False)
    if stop_active:
        sys.exit(0)

    # Read current state (fail-open).
    try:
        state = json.loads(state_file.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        sys.exit(0)

    if state.get('had_work') and not state.get('did_log'):
        # Only block if there's an active ticket to log against.
        import subprocess as sp
        try:
            proc = sp.run(
                ['kd', 'tk', 'current', '--id'],
                capture_output=True, text=True, timeout=5,
            )
            ticket_id = proc.stdout.strip()
            if proc.returncode != 0 or not ticket_id:
                sys.exit(0)  # No active ticket — fail open.
        except Exception:
            sys.exit(0)  # Timeout or error — fail open.

        result = {
            'decision': 'block',
            'reason': f\"KINGDOM: You did meaningful work this turn but didn't log it. Run: kd tk log {ticket_id} 'summary of what you did'\"
        }
        print(json.dumps(result))
" 2>/dev/null || true
    exit 0
fi
