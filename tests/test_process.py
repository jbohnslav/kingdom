"""Behavioral coverage for subprocess output capture and live logs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from subprocess import Popen
from unittest.mock import patch

import pytest

from kingdom.process import run_streaming_subprocess


def test_live_log_is_visible_before_process_exit(tmp_path: Path) -> None:
    """The child cannot finish successfully until both streams reach the live log."""
    log_path = tmp_path / "logs" / "live.log"
    script = """
import sys
import time
from pathlib import Path

log = Path(sys.argv[1])
print("stdout is live", flush=True)
print("stderr is live", file=sys.stderr, flush=True)
deadline = time.monotonic() + 2
while time.monotonic() < deadline:
    text = log.read_text() if log.exists() else ""
    if "stdout is live" in text and "stderr is live" in text:
        sys.exit(0)
    time.sleep(0.01)
sys.exit(17)
"""
    result = run_streaming_subprocess(
        [sys.executable, "-c", script, str(log_path)],
        cwd=tmp_path,
        env={},
        live_log_path=log_path,
    )

    assert result.returncode == 0, "child exited before both streams became visible in its live log"
    assert result.stdout == "stdout is live\n"
    assert result.stderr == "stderr is live\n"


def test_drains_full_pipes_and_preserves_nonzero_exit(tmp_path: Path) -> None:
    """A full stderr pipe must not block stdout capture or lose final partial lines."""
    script = """
import signal
import sys
signal.alarm(5)
assert sys.stdin.read() == ""
sys.stderr.write("error\\n" * 50000 + "stderr tail")
sys.stderr.flush()
sys.stdout.write("output\\n" * 50000 + "stdout tail")
sys.exit(9)
"""
    result = run_streaming_subprocess([sys.executable, "-c", script], cwd=tmp_path, env={})

    assert result.returncode == 9
    assert result.stdout == "output\n" * 50000 + "stdout tail"
    assert result.stderr == "error\n" * 50000 + "stderr tail"


def test_unwritable_log_does_not_spawn_child(tmp_path: Path) -> None:
    with (
        patch.object(Path, "open", side_effect=PermissionError("read only")),
        patch("kingdom.process.subprocess.Popen") as popen,
        pytest.raises(OSError, match=r"Could not open live log.*read only"),
    ):
        run_streaming_subprocess([sys.executable], cwd=tmp_path, env={}, live_log_path=tmp_path / "live.log")
    popen.assert_not_called()


def test_missing_command_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_streaming_subprocess([str(tmp_path / "missing-command")], cwd=tmp_path, env={})


@pytest.fixture
def children(monkeypatch):
    """Keep the real child handles available for cleanup assertions."""
    processes = []
    popen = subprocess.Popen

    def capture_child(*args, **kwargs):
        proc = popen(*args, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr("kingdom.process.subprocess.Popen", capture_child)
    return processes


@pytest.mark.parametrize("operation", ["write", "flush"])
def test_log_failure_kills_child_and_propagates(tmp_path: Path, children, operation: str) -> None:
    log_path = tmp_path / "live.log"
    with (
        log_path.open("a") as log,
        patch.object(Path, "open", return_value=log),
        patch.object(log, operation, side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        run_streaming_subprocess(
            [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
            cwd=tmp_path,
            env={},
            live_log_path=log_path,
        )

    assert len(children) == 1
    assert children[0].returncode is not None
    assert children[0].stdout.closed
    assert children[0].stderr.closed


def test_pipe_decode_failure_kills_child_and_propagates(tmp_path: Path, children) -> None:
    with pytest.raises(UnicodeDecodeError):
        run_streaming_subprocess(
            [
                sys.executable,
                "-c",
                "import sys, time; sys.stdout.buffer.write(bytes([255, 10])); sys.stdout.flush(); time.sleep(30)",
            ],
            cwd=tmp_path,
            env={},
        )

    assert len(children) == 1
    assert children[0].returncode is not None
    assert children[0].stdout.closed
    assert children[0].stderr.closed


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), subprocess.TimeoutExpired("agent", 1)])
def test_wait_interruption_kills_child_and_propagates(tmp_path: Path, children, interruption) -> None:
    wait = Popen.wait
    interrupted = False

    def interrupt_once(proc, *args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise interruption
        return wait(proc, *args, **kwargs)

    with patch.object(Popen, "wait", interrupt_once), pytest.raises(type(interruption)):
        run_streaming_subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path,
            env={},
        )

    assert len(children) == 1
    assert children[0].returncode is not None
    assert children[0].stdout.closed
    assert children[0].stderr.closed


@pytest.mark.parametrize("failure", ["log_write", "interrupt"])
def test_failure_terminates_descendants_holding_pipes(tmp_path: Path, children, failure: str) -> None:
    """Cleanup must not wait for a surviving descendant to close inherited pipes."""
    ready = tmp_path / "descendant-started"
    survived = tmp_path / "descendant-survived"
    script = """
import subprocess
import sys
import time
from pathlib import Path

subprocess.Popen([
    sys.executable, "-c",
    "import sys,time; from pathlib import Path; time.sleep(1); Path(sys.argv[1]).touch()",
    sys.argv[2],
])
Path(sys.argv[1]).touch()
print("ready", flush=True)
time.sleep(30)
"""
    wait = Popen.wait
    interrupted = False

    def interrupt_after_spawn(proc, *args, **kwargs):
        import time

        nonlocal interrupted
        if not interrupted:
            interrupted = True
            deadline = time.monotonic() + 5
            while not ready.exists():
                if time.monotonic() >= deadline:
                    raise AssertionError("backend never spawned its descendant")
                time.sleep(0.01)
            raise KeyboardInterrupt
        return wait(proc, *args, **kwargs)

    log_path = tmp_path / "live.log"
    with log_path.open("a") as log:
        if failure == "log_write":
            failure_patch = patch.object(log, "write", side_effect=OSError("disk full"))
            expected = OSError
        else:
            failure_patch = patch.object(Popen, "wait", interrupt_after_spawn)
            expected = KeyboardInterrupt
        with patch.object(Path, "open", return_value=log), failure_patch, pytest.raises(expected):
            run_streaming_subprocess(
                [sys.executable, "-c", script, str(ready), str(survived)],
                cwd=tmp_path,
                env={},
                live_log_path=log_path,
            )

    assert not survived.exists(), "cleanup waited for the surviving descendant to release inherited pipes"
    assert children[0].returncode is not None
    assert children[0].stdout.closed
    assert children[0].stderr.closed
