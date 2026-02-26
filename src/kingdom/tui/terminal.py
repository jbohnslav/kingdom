"""Terminal environment detection for TUI compatibility."""

from __future__ import annotations

import os
import subprocess


def in_tmux_control_mode() -> bool:
    """Detect if the current tmux session has a client in control mode (-CC).

    Returns False if not running under tmux at all.
    """
    if not os.environ.get("TMUX"):
        return False

    try:
        # Get the current session name
        session_result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if session_result.returncode != 0 or not session_result.stdout.strip():
            return False

        session_name = session_result.stdout.strip()

        # Check if any client on this session is in control mode
        client_result = subprocess.run(
            ["tmux", "list-clients", "-t", session_name, "-F", "#{client_control_mode}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if client_result.returncode != 0:
            return False

        return "1" in client_result.stdout.strip().splitlines()

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
