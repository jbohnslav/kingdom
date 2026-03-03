"""Tests for kingdom.worker module."""

from __future__ import annotations

from unittest.mock import patch


class TestWorkerExitCode:
    """Worker should return 0 for successful outcomes, 1 for failures."""

    def test_done_returns_zero(self) -> None:
        from kingdom.worker import main

        with (
            patch("kingdom.state.resolve_current_run", return_value="test-branch"),
            patch("kingdom.harness.run_agent_loop", return_value="done"),
        ):
            code = main(
                [
                    "abc1",
                    "--agent",
                    "claude",
                    "--worktree",
                    "/tmp/fake",
                    "--thread",
                    "t1",
                    "--session",
                    "s1",
                    "--base",
                    "/tmp/fake",
                ]
            )
        assert code == 0

    def test_needs_king_review_returns_zero(self) -> None:
        """needs_king_review is a successful completion — should exit 0."""
        from kingdom.worker import main

        with (
            patch("kingdom.state.resolve_current_run", return_value="test-branch"),
            patch("kingdom.harness.run_agent_loop", return_value="needs_king_review"),
        ):
            code = main(
                [
                    "abc1",
                    "--agent",
                    "claude",
                    "--worktree",
                    "/tmp/fake",
                    "--thread",
                    "t1",
                    "--session",
                    "s1",
                    "--base",
                    "/tmp/fake",
                ]
            )
        assert code == 0, "needs_king_review is a successful outcome, should exit 0"

    def test_failed_returns_one(self) -> None:
        from kingdom.worker import main

        with (
            patch("kingdom.state.resolve_current_run", return_value="test-branch"),
            patch("kingdom.harness.run_agent_loop", return_value="failed"),
        ):
            code = main(
                [
                    "abc1",
                    "--agent",
                    "claude",
                    "--worktree",
                    "/tmp/fake",
                    "--thread",
                    "t1",
                    "--session",
                    "s1",
                    "--base",
                    "/tmp/fake",
                ]
            )
        assert code == 1

    def test_stopped_returns_one(self) -> None:
        from kingdom.worker import main

        with (
            patch("kingdom.state.resolve_current_run", return_value="test-branch"),
            patch("kingdom.harness.run_agent_loop", return_value="stopped"),
        ):
            code = main(
                [
                    "abc1",
                    "--agent",
                    "claude",
                    "--worktree",
                    "/tmp/fake",
                    "--thread",
                    "t1",
                    "--session",
                    "s1",
                    "--base",
                    "/tmp/fake",
                ]
            )
        assert code == 1
