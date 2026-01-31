"""Tmux orchestration helpers for Kingdom."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable
import os


def derive_server_name(base: Path) -> str:
    return f"kd-{base.resolve().name}"


def run_tmux(server: str, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    command = ["tmux", "-L", server, *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "tmux command failed")
    return result


def list_sessions(server: str) -> list[str]:
    try:
        result = run_tmux(server, ["list-sessions", "-F", "#{session_name}"])
    except RuntimeError as exc:
        message = str(exc)
        if "No such file or directory" in message:
            return []
        raise
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def list_windows(server: str, session: str) -> list[str]:
    try:
        result = run_tmux(
            server, ["list-windows", "-t", session, "-F", "#{window_name}"]
        )
    except RuntimeError as exc:
        message = str(exc)
        if "No such file or directory" in message:
            return []
        raise
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def list_panes(server: str, target: str) -> list[str]:
    try:
        result = run_tmux(
            server, ["list-panes", "-t", target, "-F", "#{pane_index}"]
        )
    except RuntimeError as exc:
        message = str(exc)
        if "No such file or directory" in message:
            return []
        raise
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def ensure_session(server: str, session: str) -> None:
    if session in list_sessions(server):
        return
    run_tmux(server, ["new-session", "-d", "-s", session])


def ensure_window(server: str, session: str, window: str, cwd: Path | None = None) -> None:
    if window in list_windows(server, session):
        return
    command = ["new-window", "-t", session, "-n", window]
    if cwd is not None:
        command.extend(["-c", str(cwd)])
    run_tmux(server, command)


def ensure_council_layout(server: str, session: str, window: str = "council") -> None:
    ensure_window(server, session, window)
    target = f"{session}:{window}"
    panes = list_panes(server, target)
    if len(panes) >= 3:
        return

    if len(panes) < 2:
        run_tmux(server, ["split-window", "-t", target, "-h"])
    if len(list_panes(server, target)) < 3:
        run_tmux(server, ["split-window", "-t", target, "-v"])
    run_tmux(server, ["select-layout", "-t", target, "tiled"])


def send_keys(server: str, target: str, text: str) -> None:
    run_tmux(server, ["send-keys", "-t", target, text, "Enter"])


def get_pane_command(server: str, target: str) -> str:
    result = run_tmux(server, ["display-message", "-p", "-t", target, "#{pane_current_command}"])
    return result.stdout.strip()


def should_send_command(current_command: str) -> bool:
    normalized = current_command.strip().lower()
    if normalized == "":
        return True
    return normalized in {"zsh", "bash", "sh", "fish"}


def attach_window(server: str, session: str, window: str | None = None) -> None:
    target = session if window is None else f"{session}:{window}"
    tmux_env = os.environ.get("TMUX")
    if tmux_env:
        # If we're already inside the same tmux socket as `server`, switch windows.
        # If not, fall back to attaching (this nests tmux, but it's the simplest
        # behavior that still "works" from inside another tmux server).
        socket_path = tmux_env.split(",", 1)[0]
        socket_name = Path(socket_path).name
        if socket_name == server:
            run_tmux(server, ["switch-client", "-t", target])
            return
    run_tmux(server, ["attach", "-t", target])
