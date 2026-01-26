"""Tmux orchestration helpers for Kingdom."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable


def derive_server_name(base: Path) -> str:
    return f"kd-{base.resolve().name}"


def run_tmux(server: str, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    command = ["tmux", "-L", server, *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "tmux command failed")
    return result


def list_sessions(server: str) -> list[str]:
    result = run_tmux(server, ["list-sessions", "-F", "#{session_name}"])
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def list_windows(server: str, session: str) -> list[str]:
    result = run_tmux(server, ["list-windows", "-t", session, "-F", "#{window_name}"])
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def list_panes(server: str, target: str) -> list[str]:
    result = run_tmux(server, ["list-panes", "-t", target, "-F", "#{pane_index}"])
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def ensure_session(server: str, session: str) -> None:
    if session in list_sessions(server):
        return
    run_tmux(server, ["new-session", "-d", "-s", session])


def ensure_window(server: str, session: str, window: str) -> None:
    if window in list_windows(server, session):
        return
    run_tmux(server, ["new-window", "-t", session, "-n", window])


def ensure_council_layout(server: str, session: str, window: str = "council") -> None:
    ensure_window(server, session, window)
    target = f"{session}:{window}"
    panes = list_panes(server, target)
    if len(panes) >= 4:
        return

    run_tmux(server, ["split-window", "-t", target, "-h"])
    run_tmux(server, ["split-window", "-t", target, "-v"])
    run_tmux(server, ["split-window", "-t", f"{target}.1", "-v"])
    run_tmux(server, ["select-layout", "-t", target, "tiled"])


def send_keys(server: str, target: str, text: str) -> None:
    run_tmux(server, ["send-keys", "-t", target, text, "Enter"])


def attach_window(server: str, session: str, window: str | None = None) -> None:
    target = session if window is None else f"{session}:{window}"
    run_tmux(server, ["attach", "-t", target])
