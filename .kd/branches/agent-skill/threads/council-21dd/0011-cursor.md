---
from: cursor
to: king
timestamp: 2026-02-14T02:19:04Z
---

The unstaged changes implement the requested feature (increased timeout and streaming to file) by refactoring `CouncilMember.query` to use `subprocess.Popen` with background threads for reading output.

Here is the review of the changes:

### 1. Correctness of `Popen` Implementation
The implementation in `src/kingdom/council/base.py` is **correct** and robust for the intended use case.
*   **Concurrency:** It correctly uses `threading.Thread` to read `stdout` and `stderr` concurrently, preventing deadlocks that can occur with `subprocess.PIPE`.
*   **Streaming:** The `read_stdout` thread writes to the `stream_file` (if provided) and flushes after every line, ensuring real-time updates on disk.
*   **Timeout Handling:** The main thread polls `process.poll()` and checks `time.monotonic()`. If the timeout is exceeded, it explicitly calls `process.kill()` and `process.wait()`, then raises `TimeoutExpired`. This is the correct pattern for enforcing timeouts with `Popen`.
*   **Cleanup:** It properly joins the reader threads with a timeout to ensure they finish processing buffered output before the function returns. The `finally` block ensures the stream file handle is closed.

### 2. Test Mocking Pattern
The existing tests in `tests/test_council.py` use a `mock_popen` helper that returns a `MagicMock` with `poll.return_value = 0`.
*   **Compatibility:** This mock is compatible with the new implementation for **success cases**. Because `poll()` returns `0` immediately, the `while process.poll() is None:` loop is skipped, and the code proceeds to join the threads and parse the output. Existing tests will pass.
*   **Gap in Coverage:** The current mocking pattern **does not test the timeout logic**. Since the polling loop is skipped, the code that checks `time.monotonic()` and kills the process is never executed in the test suite. To test this, you would need a mock where `poll()` returns `None` for a duration longer than the timeout.

### 3. Edge Cases
*   **Partial Lines:** If a timeout occurs, the implementation correctly joins the threads (allowing them to drain remaining buffer) and returns whatever partial output was captured. This preserves intermediate work as requested.
*   **Unicode:** The `text=True` (universal newlines) argument implies default encoding (usually UTF-8). If an agent outputs non-UTF-8 binary data, the reader threads might encounter `UnicodeDecodeError`. This is unlikely for text-based agents but is a theoretical edge case.
*   **Zombie Processes:** The use of `process.wait()` after `process.kill()` ensures that the child process is reaped, preventing zombies.

### Summary
The implementation is solid and fulfills the requirements. The only significant observation is that the **timeout mechanism itself is currently untested** by the unit tests due to the nature of the `mock_popen` helper, although the logic in the code is correct.
