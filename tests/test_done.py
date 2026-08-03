from __future__ import annotations

import json
import subprocess
import unittest.mock
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.state import (
    branch_root,
    ensure_branch_layout,
    read_json,
    set_current_run,
    state_root,
    write_json,
)
from kingdom.ticket import Ticket, write_ticket


def terminal_ticket_set() -> list[Ticket]:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Ticket(id="done", status="closed", title="Completed", resolution="completed", created=created),
        Ticket(
            id="nope",
            status="closed",
            title="Won't do",
            resolution="wont-do",
            close_reason="Out of scope",
            created=created,
        ),
        Ticket(
            id="dupe",
            status="closed",
            title="Duplicate",
            resolution="duplicate",
            close_reason="Same as done",
            duplicate_of="done",
            created=created,
        ),
        Ticket(
            id="old",
            status="closed",
            title="Superseded",
            resolution="superseded",
            close_reason="Replaced by done",
            superseded_by="done",
            created=created,
        ),
        Ticket(
            id="bad",
            status="closed",
            title="Invalid request",
            resolution="invalid",
            close_reason="Request cannot be reproduced",
            created=created,
        ),
    ]


def write_terminal_tickets(tickets_dir: Path, tickets: list[Ticket]) -> None:
    for ticket in tickets:
        write_ticket(ticket, tickets_dir / f"{ticket.id}.md")


def test_done_shows_summary_with_ticket_count() -> None:
    """kd done should show how many tickets were closed."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        tickets_dir = branch_dir / "tickets"

        # Create 3 closed tickets
        for i in range(3):
            write_ticket(
                Ticket(id=f"t{i:03d}", status="closed", title=f"Ticket {i}", created=datetime.now(UTC)),
                tickets_dir / f"t{i:03d}.md",
            )

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 0
        assert "3 tickets closed" in result.output
        assert "Session cleared" in result.output


def test_done_accepts_all_terminal_resolutions_and_reports_human_breakdown() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        write_terminal_tickets(branch_dir / "tickets", terminal_ticket_set())

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 0, result.output
        assert "5 tickets closed" in result.output
        for resolution in ("completed", "wont-do", "duplicate", "superseded", "invalid"):
            assert f"1 {resolution}" in result.output
        assert "nope" in result.output
        assert "Out of scope" in result.output
        assert "dupe" in result.output
        assert "done" in result.output
        assert "old" in result.output
        assert "Replaced by done" in result.output


def test_done_json_matches_terminal_resolution_breakdown() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        write_terminal_tickets(branch_dir / "tickets", terminal_ticket_set())

        result = runner.invoke(app, ["done", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["feature"] == "test-feature"
        assert data["status"] == "done"
        assert data["tickets_closed"] == 5
        assert data["resolutions"] == {
            "completed": 1,
            "wont-do": 1,
            "duplicate": 1,
            "superseded": 1,
            "invalid": 1,
        }
        assert data["outcomes"]["wont-do"] == [
            {"id": "nope", "title": "Won't do", "reason": "Out of scope", "reference": None}
        ]
        assert data["outcomes"]["duplicate"][0]["reference"] == "done"
        assert data["outcomes"]["superseded"][0]["reference"] == "done"
        assert data["session_cleared"] is True


@pytest.mark.parametrize(
    ("ticket", "message"),
    [
        (
            Ticket(id="nope", status="closed", title="No reason", resolution="wont-do"),
            "requires close_reason",
        ),
        (
            Ticket(
                id="dupe",
                status="closed",
                title="No reference",
                resolution="duplicate",
                close_reason="Same work",
            ),
            "requires duplicate-of",
        ),
        (
            Ticket(
                id="old",
                status="closed",
                title="No reference",
                resolution="superseded",
                close_reason="Replaced",
            ),
            "requires superseded-by",
        ),
        (
            Ticket(id="bad", status="closed", title="No reason", resolution="invalid"),
            "requires close_reason",
        ),
        (
            Ticket(
                id="odd",
                status="closed",
                title="Unknown outcome",
                resolution="abandoned",
                close_reason="Unknown",
            ),
            "unknown resolution",
        ),
        (
            Ticket(
                id="mixed",
                status="closed",
                title="Mismatched evidence",
                resolution="completed",
                duplicate_of="done",
            ),
            "cannot use duplicate-of or superseded-by",
        ),
    ],
)
def test_done_rejects_invalid_terminal_evidence(ticket: Ticket, message: str) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        write_ticket(ticket, branch_dir / "tickets" / f"{ticket.id}.md")

        result = runner.invoke(app, ["done", "--force"])

        assert result.exit_code == 1
        assert message in result.output
        assert read_json(branch_dir / "state.json").get("status") != "done"
        assert (base / ".kd" / "current").exists()


def test_done_accepts_legacy_completed_duplicate_and_superseded_tickets() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        created = datetime(2026, 1, 1, tzinfo=UTC)
        write_terminal_tickets(
            branch_dir / "tickets",
            [
                Ticket(id="old1", status="closed", title="Legacy completed", created=created),
                Ticket(
                    id="old2",
                    status="closed",
                    title="Legacy duplicate",
                    duplicate_of="old1",
                    created=created,
                ),
                Ticket(
                    id="old3",
                    status="closed",
                    title="Legacy superseded",
                    superseded_by="old1",
                    created=created,
                ),
            ],
        )

        result = runner.invoke(app, ["done", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["resolutions"]["completed"] == 1
        assert data["resolutions"]["duplicate"] == 1
        assert data["resolutions"]["superseded"] == 1
        assert data["outcomes"]["duplicate"] == [
            {
                "id": "old2",
                "title": "Legacy duplicate",
                "reason": "Duplicate of old1",
                "reference": "old1",
            }
        ]
        assert data["outcomes"]["superseded"] == [
            {
                "id": "old3",
                "title": "Legacy superseded",
                "reason": "Superseded by old1",
                "reference": "old1",
            }
        ]


def test_done_shows_push_reminder_when_unpushed() -> None:
    """kd done should remind to push if there are unpushed commits."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
        subprocess.run(["git", "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)

        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        # No remote set up, so commits are "unpushed"
        result = runner.invoke(app, ["done"])

        assert result.exit_code == 0
        assert "push" in result.output.lower()


def test_done_marks_state_and_clears_current() -> None:
    """kd done sets status=done in state.json and clears current pointer."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 0
        assert "Done:" in result.output
        assert "test-feature" in result.output

        # Branch directory still exists (status-only, no move)
        branch_dir = branch_root(base, "test-feature")
        assert branch_dir.exists()

        # state.json updated
        state = read_json(branch_dir / "state.json")
        assert state["status"] == "done"
        assert "done_at" in state

        # Current pointer removed
        assert not (base / ".kd" / "current").exists()


def test_done_errors_without_active_run() -> None:
    """kd done fails when no current run is set."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        state_root(base).mkdir(parents=True)

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 1
        assert "No active session" in result.output
        assert "kd done <branch>" in result.output


def test_done_with_explicit_feature() -> None:
    """kd done <feature> works with explicit feature argument."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "explicit-feature")

        result = runner.invoke(app, ["done", "explicit-feature"])

        assert result.exit_code == 0
        assert "Done:" in result.output
        assert "explicit-feature" in result.output

        # state.json updated in place
        state = read_json(branch_root(base, "explicit-feature") / "state.json")
        assert state["status"] == "done"


def test_done_preserves_existing_state() -> None:
    """kd done preserves existing fields in state.json."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        state_path = branch_dir / "state.json"
        existing_state = {"tickets": {"T-001": "kin-abc123"}, "peasant": {"ticket": "T-001"}}
        state_path.write_text(json.dumps(existing_state, indent=2) + "\n")

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 0

        state = read_json(branch_dir / "state.json")
        assert state["status"] == "done"
        assert state["tickets"] == {"T-001": "kin-abc123"}
        assert state["peasant"] == {"ticket": "T-001"}


def test_done_timestamp_format() -> None:
    """kd done adds ISO UTC timestamp."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        before = datetime.now(UTC)
        result = runner.invoke(app, ["done"])
        after = datetime.now(UTC)

        assert result.exit_code == 0

        state = read_json(branch_root(base, "test-feature") / "state.json")
        done_at = datetime.fromisoformat(state["done_at"])

        assert before <= done_at <= after
        assert done_at.tzinfo is not None


def test_done_explicit_feature_does_not_clear_different_current() -> None:
    """kd done <other-feature> does not clear current if it's a different feature."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "current-feature")
        ensure_branch_layout(base, "other-feature")
        set_current_run(base, "current-feature")

        result = runner.invoke(app, ["done", "other-feature"])

        assert result.exit_code == 0

        current_path = base / ".kd" / "current"
        assert current_path.exists()
        assert current_path.read_text().strip() == "current-feature"


def test_done_idempotent() -> None:
    """kd done on an already-done branch succeeds (idempotent)."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "test-feature")

        # First done
        result = runner.invoke(app, ["done", "test-feature"])
        assert result.exit_code == 0

        # Second done (idempotent)
        result = runner.invoke(app, ["done", "test-feature"])
        assert result.exit_code == 0

        state = read_json(branch_root(base, "test-feature") / "state.json")
        assert state["status"] == "done"


def test_done_blocks_when_branch_has_open_tickets() -> None:
    """kd done should fail and list non-closed tickets unless forced."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        tickets_dir = branch_dir / "tickets"

        write_ticket(
            Ticket(id="kin-open1", status="open", title="Open ticket", created=datetime.now(UTC)),
            tickets_dir / "kin-open1.md",
        )
        write_ticket(
            Ticket(id="kin-prog1", status="in_progress", title="In progress ticket", created=datetime.now(UTC)),
            tickets_dir / "kin-prog1.md",
        )

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 1
        assert "Error: 2 open ticket(s) on 'test-feature':" in result.output
        assert "kin-open1" in result.output
        assert "Open ticket" in result.output
        assert "kin-prog1" in result.output
        assert "In progress ticket" in result.output
        assert "Close tickets, move them to backlog with `kd tk move`, or use --force." in result.output

        state = read_json(branch_dir / "state.json")
        assert state.get("status") != "done"
        assert (base / ".kd" / "current").exists()


def test_done_force_overrides_open_ticket_check() -> None:
    """kd done --force should succeed even if open tickets remain."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        tickets_dir = branch_dir / "tickets"
        write_ticket(
            Ticket(id="kin-open1", status="open", title="Open ticket", created=datetime.now(UTC)),
            tickets_dir / "kin-open1.md",
        )

        result = runner.invoke(app, ["done", "--force"])

        assert result.exit_code == 0
        assert "Done: test-feature" in result.output
        state = read_json(branch_dir / "state.json")
        assert state["status"] == "done"
        assert "done_at" in state
        assert not (base / ".kd" / "current").exists()


def test_done_renders_rich_panel() -> None:
    """kd done should render output inside a Rich panel with box-drawing characters."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        tickets_dir = branch_dir / "tickets"

        # Create 2 closed tickets
        for i in range(2):
            write_ticket(
                Ticket(id=f"t{i:03d}", status="closed", title=f"Ticket {i}", created=datetime.now(UTC)),
                tickets_dir / f"t{i:03d}.md",
            )

        result = runner.invoke(app, ["done"])

        assert result.exit_code == 0
        # Panel box-drawing characters present (top-left corner of rounded box)
        assert "\u256d" in result.output
        # Panel title contains branch name
        assert "Done: test-feature" in result.output
        # Panel body
        assert "2 tickets closed" in result.output
        assert "Session cleared" in result.output


def test_done_cleans_up_worktrees_from_state() -> None:
    """kd done should remove worktrees recorded in state.json, not look for directory structure."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        # Simulate worktrees created by create_worktree():
        # They're stored flat at .kd/worktrees/<ticket-id> and recorded in state.json
        wt_root = state_root(base) / "worktrees"
        wt_root.mkdir(parents=True, exist_ok=True)
        wt1 = wt_root / "tf-abc1"
        wt2 = wt_root / "tf-xyz2"
        wt1.mkdir()
        wt2.mkdir()

        # Record in state.json (as create_worktree does)
        state_path = branch_dir / "state.json"
        state = read_json(state_path) if state_path.exists() else {}
        state["worktrees"] = {
            "tf-abc1": str(wt1),
            "tf-xyz2": str(wt2),
        }
        write_json(state_path, state)

        # Patch git worktree remove so it just removes the directory
        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            if cmd[:3] == ["git", "worktree", "remove"]:
                # Simulate successful removal
                import shutil

                target = Path(cmd[-1])
                if target.exists():
                    shutil.rmtree(target)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return original_run(cmd, **kwargs)

        import unittest.mock

        with unittest.mock.patch("kingdom.cli.subprocess.run", side_effect=mock_run):
            result = runner.invoke(app, ["done", "--force"])

        assert result.exit_code == 0
        # Worktree directories should be removed
        assert not wt1.exists()
        assert not wt2.exists()
        # Worktrees map should be cleared in state.json
        state = read_json(state_path)
        assert state.get("worktrees", {}) == {}


def test_done_skips_worktree_confirm_when_not_tty() -> None:
    """kd done should skip worktree-removal confirmation when stdin is not a TTY."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        wt_root = state_root(base) / "worktrees"
        wt_root.mkdir(parents=True, exist_ok=True)
        wt1 = wt_root / "tf-abc1"
        wt1.mkdir()

        state_path = branch_dir / "state.json"
        state = read_json(state_path) if state_path.exists() else {}
        state["worktrees"] = {"tf-abc1": str(wt1)}
        write_json(state_path, state)

        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            if cmd[:3] == ["git", "worktree", "remove"]:
                import shutil

                target = Path(cmd[-1])
                if target.exists():
                    shutil.rmtree(target)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return original_run(cmd, **kwargs)

        # stdin.isatty() returns False (non-interactive) — should skip confirmation
        with (
            unittest.mock.patch("kingdom.cli.subprocess.run", side_effect=mock_run),
            unittest.mock.patch("kingdom.cli.sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False
            result = runner.invoke(app, ["done"])

        assert result.exit_code == 0
        assert not wt1.exists()
        # Should NOT have asked for confirmation
        assert "Remove" not in result.output or "worktree" not in result.output


def test_done_prompts_worktree_confirm_when_tty() -> None:
    """kd done should prompt for worktree removal when stdin IS a TTY."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        wt_root = state_root(base) / "worktrees"
        wt_root.mkdir(parents=True, exist_ok=True)
        wt1 = wt_root / "tf-abc1"
        wt1.mkdir()

        state_path = branch_dir / "state.json"
        state = read_json(state_path) if state_path.exists() else {}
        state["worktrees"] = {"tf-abc1": str(wt1)}
        write_json(state_path, state)

        # Patch sys.stdin with a mock whose isatty() returns True.
        # CliRunner replaces sys.stdin, so we patch it inside the done function.
        mock_stdin = unittest.mock.MagicMock()
        mock_stdin.isatty.return_value = True
        with (
            unittest.mock.patch("kingdom.cli.sys") as mock_sys,
            unittest.mock.patch("kingdom.cli.typer.confirm") as mock_confirm,
        ):
            mock_sys.stdin = mock_stdin
            runner.invoke(app, ["done"])

        # Confirm was called (worktree removal prompt triggered)
        mock_confirm.assert_called_once()
        assert "tf-abc1" in mock_confirm.call_args[0][0]


def test_done_blocks_open_tickets_even_when_not_tty() -> None:
    """kd done should still block on open tickets when stdin is not a TTY."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")
        tickets_dir = branch_dir / "tickets"
        write_ticket(
            Ticket(id="kin-open1", status="open", title="Open ticket", created=datetime.now(UTC)),
            tickets_dir / "kin-open1.md",
        )

        with unittest.mock.patch("kingdom.cli.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = runner.invoke(app, ["done"])

        assert result.exit_code == 1
        assert "open ticket(s)" in result.output
