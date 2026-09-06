"""Subprocess output capture shared by peasant and lord execution."""

from __future__ import annotations

import os
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, suppress
from pathlib import Path
from threading import Lock
from typing import TextIO


def run_streaming_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    live_log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Capture both pipes concurrently and flush each line to the optional log.

    Log failures, pipe errors, and parent interruption terminate the process group
    before reaping the child and draining pipes, including inherited descendant pipes.
    """
    log = None
    if live_log_path:
        try:
            live_log_path.parent.mkdir(parents=True, exist_ok=True)
            log = live_log_path.open("a", encoding="utf-8")
        except OSError as exc:
            raise OSError(f"Could not open live log {live_log_path}: {exc}") from exc

    with (
        log if log is not None else nullcontext(),
        subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            cwd=cwd,
            env=env,
            text=True,
            start_new_session=True,
        ) as proc,
    ):
        log_lock = Lock()

        def drain(stream: TextIO) -> str:
            lines: list[str] = []
            try:
                for line in stream:
                    lines.append(line)
                    if log is not None:
                        with log_lock:
                            log.write(line)
                            log.flush()
            except Exception:
                # A failed reader must not leave the child blocked on a full pipe.
                with suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                raise
            return "".join(lines)

        with ThreadPoolExecutor(max_workers=2) as readers:
            try:
                assert proc.stdout is not None and proc.stderr is not None
                stdout = readers.submit(drain, proc.stdout)
                stderr = readers.submit(drain, proc.stderr)
                proc.wait()
                return subprocess.CompletedProcess(cmd, proc.returncode, stdout.result(), stderr.result())
            except BaseException:
                # Includes KeyboardInterrupt while waiting for the backend.
                with suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise
