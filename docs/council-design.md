# Council Architecture Design

> **Status**: Implemented. Council now uses subprocess-based CLI calls. The tmux approach described in the problem statement was abandoned.

## Problem Statement

The original Council implementation tried to:
1. Run interactive agent CLIs (`claude`, `codex`, `agent`) in tmux panes
2. Paste prompts into panes via `tmux send-keys`
3. Ask LLMs to end responses with a sentinel line (`---KD_END:<uuid>---`)
4. Capture output via `tmux pipe-pane` to log files
5. Parse logs to detect the sentinel and extract responses

**This approach failed because:**
- LLMs don't reliably follow "end with this exact line" instructions
- `pipe-pane` captures raw terminal output including ANSI escape codes
- String matching for sentinels breaks due to escape sequences
- Interactive CLIs wait for more input—there's no clean "response complete" signal
- The Hand timed out even when agents did respond correctly

## What We Learned from Gastown

Steve Yegge's [Gastown](https://github.com/steveyegge/gastown) uses tmux but avoids these problems by:
- **tmux is UI, not transport**: Panes are for humans to observe, not for inter-agent communication
- **File/mail-based messaging**: Agents communicate via `gt mail` (Beads stored in git), not terminal I/O
- **Process-based detection**: `IsClaudeRunning()` checks what process is running, not output content
- **Prompt detection for readiness**: `WaitForRuntimeReady()` looks for CLI prompts, not sentinels

Key insight: **Don't use tmux as a message bus.**

## CLI Capabilities Discovery

All target CLIs support headless operation, but **JSON formats and session continuation differ**.

| CLI | Headless Mode | Machine Output | Session Continuation |
|-----|---------------|----------------|----------------------|
| Claude Code | `--print` | `--output-format json` | `--resume <session_id>` (avoid `--continue`) |
| Codex | `codex exec` | `--json` (JSONL events), `--output-last-message <file>` | **Not supported** by current `codex exec` (treat as stateless) |
| Cursor Agent | `--print` | `--output-format json` | `--resume [chatId]` |
| Gemini CLI | `-p`/`--prompt` | `--output-format json` | `--resume` |

**Note**: CLI flags and schemas drift. Treat each CLI as an integration with its own contract, and validate via `--help` + tiny “OK” smoke calls.

**MVP scope**: Claude, Codex, Cursor Agent. Gemini support is future work.

**Session continuation is the key feature**: it allows multi-turn conversations (5-10+ exchanges) without re-sending the entire conversation history. Each CLI manages its own session storage.

## New Architecture

### Core Principle

**Subprocess + JSON + Session IDs**

```
Hand (Python REPL)
  │
  ├─► claude --print --output-format json --continue <session> -p "prompt"
  ├─► codex exec --output json --resume <session> -p "prompt"
  └─► cursor agent --output-format json --resume <session> -p "prompt"
      │
      └─► JSON response with session_id for next turn
```

No tmux in the critical path. No sentinel detection. No ANSI parsing.

### Components

#### Why Subclasses?

Each CLI has different flags, JSON response structures, and quirks:

| Aspect | Claude | Codex | Cursor Agent |
|--------|--------|-------|--------------|
| Base command | `claude --print` | `codex exec` | `cursor agent` |
| JSON flag | `--output-format json` | `--json` (JSONL), or `--output-last-message <file>` | `--output-format json` |
| Prompt | `-p "prompt"` | positional prompt arg | positional prompt arg |
| Continue flag | `--resume <session_id>` | *(none in current CLI)* | `--resume [chatId]` |
| Response text | JSON `result` | last-message file contents OR final JSONL agent message | JSON `result` |
| Session ID | JSON `session_id` | *(none in current CLI)* | JSON `session_id` |

A config-based approach would require a lot of conditional logic. Subclasses keep each CLI's quirks isolated and make it easy to add new agents.

#### Class Hierarchy

```
CouncilMember (ABC)
├── ClaudeMember      # claude --print --output-format json
├── CodexMember       # codex exec --output json
├── CursorAgentMember # cursor agent --output-format json
└── GeminiMember      # gemini -p --output-format json (future)
```

#### CouncilMember (Base Class)

Abstract base class handling common logic:
- Subprocess execution with timeout
- Logging to file for optional UI
- Session ID storage and retrieval

```python
class CouncilMember(ABC):
    """Base class for council agents."""

    name: str                       # e.g., "claude", "codex", "agent"
    session_id: str | None = None   # for --continue/--resume
    log_path: Path | None = None    # for optional tmux viewing

    @abstractmethod
    def build_command(self, prompt: str) -> list[str]:
        """Build the CLI command with appropriate flags."""
        ...

    @abstractmethod
    def parse_response(self, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
        """Parse CLI output. Returns (text, new_session_id, error)."""
        ...

    def query(self, prompt: str, timeout: int = 300) -> AgentResponse:
        """Send prompt and get response. Handles subprocess and logging."""
        start = time.monotonic()
        cmd = self.build_command(prompt)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            text, new_session, error = self.parse_response(
                result.stdout, result.stderr, result.returncode
            )
        except subprocess.TimeoutExpired:
            text, new_session, error = "", None, f"Timeout after {timeout}s"

        if new_session:
            self.session_id = new_session

        elapsed = time.monotonic() - start
        self._log(prompt, text, error, elapsed)

        return AgentResponse(name=self.name, text=text, error=error, elapsed=elapsed)

    def reset_session(self) -> None:
        """Clear session to start fresh conversation."""
        self.session_id = None

    def _log(self, prompt: str, text: str, error: str, elapsed: float) -> None:
        """Append to log file if configured."""
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n>>> {prompt}\n")
            if error:
                f.write(f"ERROR: {error}\n")
            if text:
                f.write(f"{text}\n")
            f.write(f"({elapsed:.1f}s)\n")
```

#### ClaudeMember

Claude Code specific implementation:

```python
class ClaudeMember(CouncilMember):
    name = "claude"

    def build_command(self, prompt: str) -> list[str]:
        cmd = ["claude", "--print", "--output-format", "json", "-p", prompt]
        if self.session_id:
            cmd.extend(["--continue", self.session_id])
        return cmd

    def parse_response(self, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
        if code != 0:
            return "", None, stderr.strip() or f"Exit code {code}"
        try:
            data = json.loads(stdout)
            text = data.get("result", "")
            session_id = data.get("session_id")
            return text, session_id, ""
        except json.JSONDecodeError as e:
            return stdout, None, f"JSON parse error: {e}"
```

#### CodexMember

OpenAI Codex CLI specific implementation:

```python
class CodexMember(CouncilMember):
    name = "codex"

    def build_command(self, prompt: str) -> list[str]:
        cmd = ["codex", "exec", "--output-last-message", "<tmpfile>", prompt]
        return cmd

    def parse_response(self, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
        # Codex's most reliable "response text" signal is the output-last-message file.
        # (Optional) stdout can be streamed as JSONL via --json, but that requires event parsing.
        ...
```

#### CursorAgentMember

Cursor Agent CLI specific implementation:

```python
class CursorAgentMember(CouncilMember):
    name = "agent"

    def build_command(self, prompt: str) -> list[str]:
        cmd = ["cursor", "agent", "--output-format", "json", "-p", prompt]
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        return cmd

    def parse_response(self, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
        if code != 0:
            return "", None, stderr.strip() or f"Exit code {code}"
        try:
            data = json.loads(stdout)
            # Cursor's JSON output uses "result" for the response text.
            text = data.get("result", "") or data.get("text", "") or data.get("response", "")
            session_id = data.get("session_id") or data.get("conversation_id")
            return text, session_id, ""
        except json.JSONDecodeError as e:
            return stdout, None, f"JSON parse error: {e}"
```

#### Council

Orchestrates parallel queries across all members:

```python
@dataclass
class Council:
    members: list[CouncilMember]
    timeout: int = 300

    @classmethod
    def create(cls, logs_dir: Path | None = None) -> Council:
        """Create council with default members."""
        members = []
        for member_cls in [ClaudeMember, CodexMember, CursorAgentMember]:
            member = member_cls()
            if logs_dir:
                member.log_path = logs_dir / f"council-{member.name}.log"
            members.append(member)
        return cls(members=members)

    def query(self, prompt: str) -> dict[str, AgentResponse]:
        """Query all members in parallel."""
        with ThreadPoolExecutor(max_workers=len(self.members)) as pool:
            futures = {
                pool.submit(m.query, prompt, self.timeout): m.name
                for m in self.members
            }
            return {futures[f]: f.result() for f in as_completed(futures)}

    def reset_sessions(self) -> None:
        """Clear all sessions for fresh conversation."""
        for m in self.members:
            m.reset_session()
```

#### Hand

REPL that coordinates user interaction:
- Receives user prompts
- Dispatches to Council
- Displays/synthesizes responses
- Logs interactions

### File Layout

```
src/kingdom/
├── council/
│   ├── __init__.py       # exports Council, AgentResponse
│   ├── base.py           # CouncilMember ABC, AgentResponse
│   ├── claude.py         # ClaudeMember
│   ├── codex.py          # CodexMember
│   ├── cursor.py         # CursorAgentMember
│   └── gemini.py         # GeminiMember (future)
├── hand.py               # Hand REPL using Council
└── cli.py                # kd commands
```

Each CLI gets its own file. Adding a new agent = add one file + register in `__init__.py`.

### Session Continuity

Each agent maintains its own session, keyed implicitly by the session ID returned from previous calls:

```
Turn 1: claude --print -p "Analyze OAuth refresh"
        → returns session_id: "abc123"

Turn 2: claude --print --continue abc123 -p "Focus on token storage"
        → continues same conversation, returns session_id: "abc124"

Turn 3: claude --print --continue abc124 -p "Draft the implementation"
        → continues same conversation
```

The CLI handles context management. We just pass the session ID forward.

### Logging for Optional UI

Each `CouncilMember` writes to a log file:

```
.kd/runs/<feature>/logs/
├── council-claude.log    # append-only log of claude interactions
├── council-codex.log     # append-only log of codex interactions
├── council-agent.log     # append-only log of agent interactions
└── hand.jsonl            # structured log of Hand sessions
```

Log format (simple, human-readable):
```
>>> What's the best approach for OAuth refresh?
OAuth refresh tokens should be stored securely...
(2.3s)

>>> Focus on token storage options
There are three main approaches...
(1.8s)
```

### Optional tmux UI

tmux becomes **optional viewing**, not communication:

| Command | What It Does |
|---------|--------------|
| `kd council` | Query council via subprocess (no tmux needed) |
| `kd attach council` | Open tmux with panes tailing log files |
| `kd chat claude` | Interactive session with one agent (tmux pane) |

For `kd attach council`, create a tmux window with panes running:
```bash
tail -f .kd/runs/<feature>/logs/council-claude.log
tail -f .kd/runs/<feature>/logs/council-codex.log
tail -f .kd/runs/<feature>/logs/council-agent.log
```

Users can watch agents "think" in real-time, but the actual communication is subprocess-based.

## State Layout (Updated)

```
.kd/
├── current                     # current feature name
├── config.json                 # global config
└── branches/
    └── <feature>/
        ├── state.json          # run state, ticket mappings
        ├── design.md           # design document (includes Breakdown section)
        ├── tickets/            # ticket specs
        │   └── kin-*.md
        ├── sessions/           # session ID storage
        │   ├── claude.session  # session ID for claude
        │   ├── codex.session   # session ID for codex
        │   └── agent.session   # session ID for agent
        └── logs/
            ├── council-claude.log
            ├── council-codex.log
            └── council-agent.log
```

Session files contain just the session ID string, enabling persistence across `kd` invocations.

## Commands (Updated)

| Command | Description |
|---------|-------------|
| `kd start <feature>` | Initialize run, state, tmux session |
| `kd chat` | Start Hand REPL (queries Council via subprocess) |
| `kd council "prompt"` | One-shot Council query from command line |
| `kd council --reset` | Clear sessions, start fresh conversation |
| `kd attach council` | Open tmux panes tailing Council logs |
| `kd attach hand` | Attach to Hand tmux window |
| `kd chat claude` | Direct interactive chat with one agent |

## Example Session

```
$ kd start oauth-refresh
Initialized run: .kd/runs/oauth-refresh/
Tmux: server=kd-kingdom session=oauth-refresh

$ kd chat
hand> What's the best approach for OAuth refresh token handling?

[claude] (2.1s)
OAuth refresh tokens should be stored encrypted at rest...

[codex] (1.8s)
For refresh token management, consider using...

[agent] (2.4s)
The recommended approach for OAuth refresh...

hand> Focus on the token storage comparison

[claude] (1.5s)
Comparing the three storage options...
(continues same conversation - no re-sending history)

hand> /reset
Sessions cleared. Starting fresh conversation.

hand> exit
```

## Why This Is Better

| Aspect | Old (Sentinel) | New (Subprocess) |
|--------|----------------|------------------|
| Reliability | LLM must follow instructions | Deterministic subprocess |
| Output parsing | ANSI escape codes break matching | Clean JSON |
| Completion detection | Hope for sentinel in stream | Subprocess exit |
| Multi-turn | Broken (stateless panes) | Session continuation |
| Debugging | Parse tmux logs | Read clean log files |
| Complexity | tmux + pipe-pane + polling | subprocess.run() |

## Open Questions

1. **Synthesis**: How should Hand synthesize multiple responses? Options:
   - Display all responses, let user decide
   - Call a synthesis model (e.g., `claude --print` with all responses)
   - Simple heuristic (longest response, majority vote on structure)

2. **Timeout handling**: What to do when one agent times out but others respond?
   - Show partial results with error indicator
   - Retry timed-out agent
   - Continue without it

3. **Agent availability**: What if an agent CLI isn't installed?
   - Skip with warning
   - Fail fast
   - Configurable in `.kd/config.json`

4. **Session persistence**: Should sessions persist across `kd start` invocations?
   - Current design: sessions live in `runs/<feature>/sessions/`
   - Alternative: global sessions in `.kd/sessions/`

5. **CLI flag verification**: The exact headless/JSON/continue flags need testing against current CLI versions. What's our fallback if a CLI doesn't support expected flags?
   - Disable that agent with warning
   - Fall back to interactive tmux mode for that agent
   - Make it configurable per-agent in config

6. **Streaming output**: Should we support streaming responses for long-running queries?
   - Current design: wait for full response
   - Alternative: stream to log file, display incrementally

## Implementation Plan

1. Create `kingdom/council/` package:
   - `base.py`: `CouncilMember` ABC, `AgentResponse` dataclass
   - `claude.py`: `ClaudeMember` implementation
   - `codex.py`: `CodexMember` implementation
   - `cursor.py`: `CursorAgentMember` implementation
   - `__init__.py`: exports `Council`, `AgentResponse`, member classes

2. Update `kingdom/hand.py` to use subprocess-based Council

3. Add session persistence:
   - Save session IDs to `.kd/runs/<feature>/sessions/<agent>.session`
   - Load on Council initialization
   - Save after each query

4. Update CLI commands:
   - `kd council "prompt"`: one-shot Council query
   - `kd council --reset`: clear sessions
   - `kd attach council`: tmux panes tailing logs
   - `kd chat <agent>`: direct interactive mode with one agent

5. Remove old sentinel-based code:
   - Delete `council_worker.py`
   - Remove `pipe-pane` logic from `tmux.py`
   - Clean up old Hand implementation

---

## Implementation Log

### 2026-01-27: Initial Implementation

Implemented the subprocess-based architecture. Found several bugs during testing:

#### Bugs Fixed

1. **Codex CLI flags incorrect**: `codex exec` doesn't support `--output json` or `-p`. Fixed to use positional prompt.

2. **Cursor CLI missing `--print`**: Cursor agent requires `--print` for non-interactive use. Prompt is positional, not `-p`.

3. **Claude `--continue` leaks sessions**: `--continue` continues "most recent conversation in directory" (including the Claude Code session running `kd`!). Fixed to use `--resume <session_id>`.

4. **JSON parsing crashes on non-dict**: `json.loads('"hello"')` returns a string, then `.get()` fails. Added `isinstance(data, dict)` check.

#### Correct CLI Commands (Verified)

| Agent | Command |
|-------|---------|
| Claude (new) | `claude --print --output-format json -p "prompt"` |
| Claude (resume) | `claude --print --output-format json -p "prompt" --resume <session_id>` |
| Codex (new) | `codex exec --json "prompt"` |
| Codex (resume) | `codex exec resume <thread_id> --json "prompt"` |
| Cursor (new) | `cursor agent --print --output-format json "prompt"` |
| Cursor (resume) | `cursor agent --print --output-format json "prompt" --resume <session_id>` |

#### Current Status

| Agent | Works? | Session Continuity |
|-------|--------|-------------------|
| Claude | ✅ | ✅ Working |
| Codex | ✅ | ✅ Working (via `exec resume <thread_id>`) |
| Cursor | ✅ | ✅ Working (via `--resume <session_id>`) |

All three agents now parse correctly and support session continuation.

**Final fixes applied:**
- Claude: `--resume` must come before `-p` in argument order
- Codex: Use `codex exec resume <thread_id> --json "prompt"` and parse JSONL for `thread.started` event
- Cursor: Check `result` key first (not `text`/`response`)

**Verified working (2026-01-30):**
```
hand> remember: the secret word is pineapple
[claude] I'll remember that...
[codex] Got it — I'll treat `pineapple` as the secret word...
[agent] I have noted that the secret word is **pineapple**. 🍍

hand> what's the secret word?
[claude] The secret word is **pineapple**.
[codex] pineapple
[agent] The secret word is pineapple
```

---

## Fix Plan (Failing-First)

This plan is intentionally structured to start with things that should **fail in the current implementation**, then move to the smallest fixes that make them pass.

### 1) Add failing tests that reproduce today’s breakage

1. **Cursor JSON parsing**: add a test case where stdout is:
   - `{"type":"result","subtype":"success","is_error":false,"result":"OK","session_id":"..."}`
   - Expect: parsed text = `"OK"`, session id extracted.
   - Current behavior: text comes back empty because the parser ignores `result`.

2. **Codex JSONL parsing / last-message**: add a test fixture using the first few lines from:
   - `codex exec --json "Return exactly OK"`
   - Expect: parsed text = `"OK"` (from the final `agent_message` event), or (preferred) validate that we *do not* treat JSONL as a dict.
   - Current behavior: `json.loads(stdout)` fails (or returns nonsense if only one line is passed).

### 2) Fix Cursor integration

- Update Cursor parsing to prefer:
  - response text: `result` (fallback to `text`/`response`)
  - session id: `session_id` (fallback to `conversation_id`)
- Ensure “success exit + empty text” is treated as an error with raw captured for debugging.

### 3) Fix Codex integration (stateless + deterministic output)

- Stop trying to use `--resume` (not supported in current Codex CLI).
- Prefer `--output-last-message <file>` to get response text deterministically.
- (Optional) keep `--json` for debug, but if used, parse JSONL events and extract the final `agent_message`.

### 4) Make “empty response” loud

- Change the parsing contract so members can return an explicit error message (not just empty text).
- In base query logic, if exit code is 0 but response is empty and raw output looks structured, surface an error like:
  - `"Parsed empty response (unexpected schema). See raw output."`

### 5) Update docs + reality checks

- Update this document’s “Capabilities” tables and “Correct CLI commands” to match verified `--help` output.
- Add a tiny “OK” smoke check per CLI as the standard way to re-verify flags after upgrades.
