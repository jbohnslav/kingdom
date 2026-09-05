"""Removing a moved ticket's lock must not strand waiters on an old inode."""

import fcntl
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, get_ident

import pytest

from kingdom.state import flock


@pytest.mark.parametrize("timeout", [None, 2.0])
def test_waiter_reopens_removed_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: float | None) -> None:
    lock_path = tmp_path / ".ticket.md.lock"
    waiting = Event()
    entered = Event()
    owner = get_ident()
    original_flock = fcntl.flock

    def observed_flock(fd: int, operation: int) -> None:
        if get_ident() != owner and operation & fcntl.LOCK_EX:
            waiting.set()
        original_flock(fd, operation)

    def wait_for_lock() -> None:
        with flock(lock_path, timeout_seconds=timeout):
            entered.set()

    monkeypatch.setattr(fcntl, "flock", observed_flock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old_lock = flock(lock_path)
        old_lock.__enter__()
        try:
            future = pool.submit(wait_for_lock)
            assert waiting.wait(timeout=2)
            lock_path.unlink()
            with flock(lock_path):
                old_lock.__exit__(None, None, None)
                assert not entered.wait(timeout=0.2), "Waiter entered through the deleted lock inode"
        finally:
            old_lock.__exit__(None, None, None)
        future.result(timeout=3)
    assert entered.is_set()
