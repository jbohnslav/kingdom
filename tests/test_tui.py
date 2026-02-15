"""Tests for TUI module and kd chat CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.session import get_current_thread, set_current_thread
from kingdom.state import ensure_branch_layout
from kingdom.thread import create_thread

runner = CliRunner()

BRANCH = "feature/test-chat"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    return tmp_path


class TestRequireTextual:
    def test_import_succeeds_when_installed(self) -> None:
        from kingdom.tui import require_textual

        # Should not raise
        require_textual()

    def test_import_raises_when_missing(self) -> None:
        from kingdom.tui import require_textual

        with patch.dict("sys.modules", {"textual": None}), pytest.raises(SystemExit, match="uv sync --group chat"):
            require_textual()


class TestChatCommand:
    def test_help(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "Thread ID to open" in result.output

    def test_nonexistent_thread(self, project: Path) -> None:
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat", "nonexistent"])
        assert result.exit_code == 1
        assert "Thread not found" in result.output

    def test_no_args_no_threads(self, project: Path) -> None:
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "kd chat --new" in result.output

    def test_no_args_lists_threads(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-abc1", ["king", "claude"], "council")
        create_thread(project, BRANCH, "council-abc2", ["king", "codex"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "council-abc1" in result.output
        assert "council-abc2" in result.output

    def test_new_creates_thread_and_launches(self, project: Path) -> None:
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat", "--new"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

        # Check thread was created and current_thread was set
        current = get_current_thread(project, BRANCH)
        assert current is not None
        assert current.startswith("council-")

    def test_explicit_thread_id_launches(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-test", ["king", "claude"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat", "council-test"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_resumes_current_thread(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-resume", ["king", "claude"], "council")
        set_current_thread(project, BRANCH, "council-resume")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_stale_current_thread_falls_back_to_list(self, project: Path) -> None:
        set_current_thread(project, BRANCH, "council-gone")
        create_thread(project, BRANCH, "council-other", ["king", "claude"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "council-other" in result.output


class TestChatApp:
    def test_app_stores_params(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.base == Path("/tmp")
        assert app_instance.branch == "main"
        assert app_instance.thread_id == "council-abc"

    def test_app_has_auto_scroll(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.auto_scroll is True

    def test_app_has_poller_none_before_mount(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.poller is None


class TestChatAppLayout:
    """Test the widget layout of ChatApp."""

    def test_member_names_loaded(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-layout", ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-layout")
        # Compose triggers member loading
        widgets = list(app_instance.compose())
        assert app_instance.member_names == ["claude", "codex"]
        assert len(widgets) == 4  # header, message log, status bar, input area

    def test_header_shows_thread_info(self, project: Path) -> None:
        from textual.widgets import Static

        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-hdr", ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-hdr")
        widgets = list(app_instance.compose())
        header = widgets[0]
        assert isinstance(header, Static)
        # Static stores content as _content or via update(); check the id
        assert header.id == "header-bar"
