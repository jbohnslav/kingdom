# Work Log: Subagent Debugging Investigation

## Issue
`kd council ask` times out on claude and agent (600s) while codex responds quickly (27-30s).

## What We Tried

### 1. Verified CLIs work directly
```bash
claude --print --output-format json -p "Say hello"  # 1.8s ✓
cursor agent --print --output-format json "Say hello"  # 12.6s ✓
```
Both CLIs work fine with simple prompts.

### 2. Tested with longer prompts
```bash
claude --print ... -p "Review this design... [3400 chars]"  # 7.5s ✓
cursor agent --print ... "[same prompt]"  # 29s ✓
```
Both work with realistic prompt lengths.

### 3. Checked for unexpanded shell syntax issue
The prompts in metadata.json showed literal `$(cat .kd/.../design.md)` unexpanded (user used `<<'EOF'` single-quoted heredoc). But:
- Claude handles literal `$(cat ...)` fine — it uses tools to read the file (3 turns)
- Codex also handles it — responded with actual design doc content
- Direct CLI calls with literal `$(cat ...)` work in ~7-30s

### 4. Checked session resumption
- No stale sessions for claude/agent on this branch
- Invalid session IDs fail fast with clear error, don't hang

### 5. Tested subprocess.run pattern
```python
subprocess.run(['claude', '--print', '-p', prompt], capture_output=True, text=True, timeout=60)
```
Works fine (4.1s) — same pattern Kingdom uses.

## What We Haven't Tried Yet
- Running `kd council ask` with debug logging to see exact subprocess behavior
- Checking if there's something different about the ThreadPoolExecutor context
- Testing with `--dangerously-skip-permissions` to rule out permission prompts
- Checking if claude/agent are waiting for stdin (tty detection issue?)

## Current Hypothesis
The CLIs themselves work. Something about the execution context when Kingdom spawns them via ThreadPoolExecutor might be different:
- TTY detection causing interactive mode?
- Stdin not being properly closed?
- Environment variable differences?

## Next Steps
1. Add verbose logging to council query to see subprocess args and environment
2. Test with explicit stdin handling (`stdin=subprocess.DEVNULL`)
3. Check if `--dangerously-skip-permissions` changes behavior
