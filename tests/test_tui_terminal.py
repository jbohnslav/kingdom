"""Tests for terminal environment detection."""

from __future__ import annotations

import subprocess as subprocess_mod
from subprocess import CompletedProcess
from unittest.mock import patch

from kingdom.tui.terminal import in_tmux_control_mode

TMUX_ENV = {"TMUX": "/tmp/tmux-1000/default,123,0"}


class TestInTmuxControlMode:
    def test_not_in_tmux(self) -> None:
        """Returns False when TMUX env var is not set."""
        with patch.dict("os.environ", {}, clear=True):
            assert in_tmux_control_mode() is False

    def test_tmux_no_control_mode(self) -> None:
        """Returns False for a normal tmux session (no -CC client)."""
        with (
            patch.dict("os.environ", TMUX_ENV),
            patch("kingdom.tui.terminal.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [
                CompletedProcess(args=[], returncode=0, stdout="main\n"),
                CompletedProcess(args=[], returncode=0, stdout="0\n"),
            ]
            assert in_tmux_control_mode() is False

    def test_tmux_control_mode_detected(self) -> None:
        """Returns True when a client is in control mode (-CC)."""
        with (
            patch.dict("os.environ", TMUX_ENV),
            patch("kingdom.tui.terminal.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [
                CompletedProcess(args=[], returncode=0, stdout="main\n"),
                CompletedProcess(args=[], returncode=0, stdout="0\n1\n"),
            ]
            assert in_tmux_control_mode() is True

    def test_tmux_multiple_clients_one_control(self) -> None:
        """Returns True if any client is in control mode, even among normal clients."""
        with (
            patch.dict("os.environ", TMUX_ENV),
            patch("kingdom.tui.terminal.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [
                CompletedProcess(args=[], returncode=0, stdout="work\n"),
                CompletedProcess(args=[], returncode=0, stdout="0\n0\n1\n0\n"),
            ]
            assert in_tmux_control_mode() is True

    def test_tmux_session_query_fails(self) -> None:
        """Returns False if tmux display-message fails."""
        with (
            patch.dict("os.environ", TMUX_ENV),
            patch("kingdom.tui.terminal.subprocess.run") as mock_run,
        ):
            mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="")
            assert in_tmux_control_mode() is False

    def test_tmux_not_installed(self) -> None:
        """Returns False if tmux binary is not found."""
        with (
            patch.dict("os.environ", TMUX_ENV),
            patch("kingdom.tui.terminal.subprocess.run", side_effect=FileNotFoundError),
        ):
            assert in_tmux_control_mode() is False

    def test_tmux_command_timeout(self) -> None:
        """Returns False if tmux command times out."""
        with (
            patch.dict("os.environ", TMUX_ENV),
            patch(
                "kingdom.tui.terminal.subprocess.run",
                side_effect=subprocess_mod.TimeoutExpired("tmux", 3),
            ),
        ):
            assert in_tmux_control_mode() is False
