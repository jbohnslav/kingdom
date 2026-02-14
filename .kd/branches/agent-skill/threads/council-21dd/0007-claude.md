---
from: claude
to: king
timestamp: 2026-02-14T02:05:45Z
---

Here's my review:

## Overview

Cursor implemented two things: (1) timeout bump from 300s → 600s, and (2) a streaming-to-file mechanism using `select()` + `Popen`. The timeout bump is fine. The streaming implementation has issues.

## What's Good

- **Timeout bump** — all four locations updated consistently (cli.py default, council.py default, worker.py default, and the `query()` signature). Clean.
- **Partial output on timeout** — the `TimeoutExpired` handler now captures what was accumulated instead of returning empty string. That's the right idea.
- **Stream files are cleaned up** on success via `stream_path.unlink()`.

## Problems

### 1. `select()` + `readline()` mismatch — potential deadlock/data loss

`select()` tells you a file descriptor has *bytes* available, but then `readline()` is called, which blocks until a `\n` is found. If the process writes partial lines (common with LLM streaming), `select()` fires, `readline()` blocks waiting for `\n`, and the loop stalls. This defeats the purpose of using `select()` in the first place.

Should either use `os.read()` on raw fds (non-blocking, chunk-based) or skip `select()` entirely and just use threads to read stdout/stderr concurrently.

### 2. Drain race after process exits

When `select()` returns empty and `process.poll() is not None`, it breaks immediately. But there can still be buffered data in the pipes that hasn't been read. The giant comment block in the code (`# Process finished, but maybe some data left in buffers?`) shows Cursor knew this was a problem but didn't solve it. This means the final chunk of output can be silently dropped.

### 3. Stream file opened/closed per line

```python
with stream_path.open("a", encoding="utf-8") as f:
    f.write(line)
```

This opens and closes the file on every single line. Over a multi-minute council response, that's thousands of open/close cycles. Should open once and flush periodically.

### 4. `.stream-{name}.md` files are dot-prefixed but not gitignored

These are temp files in the thread directory. If someone commits mid-query, they'd get picked up. They should either go in the `logs/` directory (which is gitignored) or be added to `.gitignore`.

### 5. No resume logic

The ticket says "wire up the resume logic" — the ability to say "continue where you left off" using the partial output. This implementation streams to a file and then deletes it on completion, but there's no code path that reads the stream file on a subsequent query to provide context. The plumbing is half-done: it captures partials but doesn't use them.

### 6. `process.stdout = None` mutation

Setting `process.stdout = None` to signal EOF is fragile — it mutates the Popen object's internals. If `process.wait()` or `process.communicate()` later tries to access `.stdout`, it could behave unexpectedly. The timeout handler calls `process.communicate()` which will fail if stdout was already set to None.

### 7. `process` may be unbound in timeout handler

If the `TimeoutExpired` exception fires, the handler references `process` and calls `process.communicate()`. But if the exception somehow fires before `process = subprocess.Popen(...)` completes (unlikely but possible with signals), `process` would be unbound. The `text_accumulator` / `error_accumulator` are initialized before the try block, but `process` is not.

## Recommendation

The timeout bump is fine — keep it. The streaming implementation needs rework. The `select()` + `readline()` approach is the wrong pattern. A cleaner approach would be:

- Use `Popen` with two reader threads (one for stdout, one for stderr) that do blocking `readline()` and append to accumulators + tee to file
- Or use `asyncio.subprocess` with proper stream readers
- Store partial output in `logs/` (gitignored) not in thread dirs
- Actually implement the resume logic, or don't claim streaming support yet

As-is, this could deadlock on partial lines and silently drop output. I'd suggest keeping only the timeout bump and reworking the streaming piece.
