"""Tests for the refactored council CLI commands (threads-based)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kingdom import cli
from kingdom.council.base import AgentResponse
from kingdom.session import get_current_thread, set_current_thread
from kingdom.state import ensure_branch_layout, set_current_run
from kingdom.thread import list_messages

runner = CliRunner()

BRANCH = "feature/council-test"


def setup_project(base: Path) -> None:
    """Create a minimal project ready for council commands."""
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


def mock_council_query(responses: dict[str, AgentResponse]):
    """Return a patch that makes Council.query return the given responses."""
    return patch.object(
        cli.Council,
        "query",
        return_value=responses,
    )


def make_responses(*names: str) -> dict[str, AgentResponse]:
    """Build mock responses for given agent names."""
    return {name: AgentResponse(name=name, text=f"Response from {name}", elapsed=1.0) for name in names}


class TestCouncilAsk:
    def test_ask_creates_thread_on_first_use(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                result = runner.invoke(cli.app, ["council", "ask", "What is caching?"])

            assert result.exit_code == 0, result.output
            assert "Thread:" in result.output

            # Thread should have been created
            current = get_current_thread(base, BRANCH)
            assert current is not None
            assert current.startswith("council-")

            # Messages should exist: 1 king + 3 responses = 4
            messages = list_messages(base, BRANCH, current)
            assert len(messages) == 4
            assert messages[0].from_ == "king"
            assert messages[0].body == "What is caching?"

    def test_ask_continues_existing_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "First question"])
                result = runner.invoke(cli.app, ["council", "ask", "Follow up"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            # 2 king messages + 6 responses = 8
            assert len(messages) == 8
            assert messages[0].body == "First question"
            assert messages[4].body == "Follow up"

    def test_ask_thread_new_starts_fresh(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "First topic"])
                first_thread = get_current_thread(base, BRANCH)

                runner.invoke(cli.app, ["council", "ask", "--thread", "new", "New topic"])
                second_thread = get_current_thread(base, BRANCH)

            assert first_thread != second_thread
            assert second_thread.startswith("council-")

            # Each thread should have 4 messages
            assert len(list_messages(base, BRANCH, first_thread)) == 4
            assert len(list_messages(base, BRANCH, second_thread)) == 4

    def test_ask_to_specific_member(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            mock_result = MagicMock()
            mock_result.stdout = '{"result": "Codex response", "session_id": "s1"}'
            mock_result.stderr = ""
            mock_result.returncode = 0

            with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
                result = runner.invoke(cli.app, ["council", "ask", "--to", "codex", "Tell me more"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            # 1 king + 1 codex = 2
            assert len(messages) == 2
            assert messages[0].to == "codex"
            assert messages[1].from_ == "codex"

    def test_ask_to_unknown_member_fails(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "ask", "--to", "unknown", "Hello"])

            assert result.exit_code == 1
            assert "Unknown member" in result.output

    def test_ask_invalid_thread_value_fails(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "ask", "--thread", "nw", "Hello"])

            assert result.exit_code == 1
            assert "Invalid --thread value" in result.output

    def test_ask_stale_current_thread_recovers(self) -> None:
        """If current_thread points to a missing directory, ask creates a new thread."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Set a stale pointer
            set_current_thread(base, BRANCH, "council-gone")

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                result = runner.invoke(cli.app, ["council", "ask", "After stale"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            assert current is not None
            assert current != "council-gone"
            assert current.startswith("council-")

    def test_ask_json_output(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                result = runner.invoke(cli.app, ["council", "ask", "--json", "Test"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "thread_id" in data
            assert "responses" in data
            assert "claude" in data["responses"]

    def test_ask_saves_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "Test"])

            from kingdom.session import get_agent_state

            # Sessions should have been saved (even if resume_id is None,
            # the save_sessions call should not error)
            state = get_agent_state(base, BRANCH, "claude")
            assert state.name == "claude"


class TestCouncilShow:
    def test_show_current_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create a thread with messages
            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "What is caching?"])

            result = runner.invoke(cli.app, ["council", "show"])

            assert result.exit_code == 0
            assert "Thread:" in result.output
            assert "king" in result.output

    def test_show_specific_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "Question 1"])
                thread_id = get_current_thread(base, BRANCH)

            result = runner.invoke(cli.app, ["council", "show", thread_id])

            assert result.exit_code == 0
            assert thread_id in result.output

    def test_show_no_thread_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show"])

            assert result.exit_code == 1
            assert "No current council thread" in result.output

    def test_show_legacy_run_fallback(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            from kingdom.state import council_logs_root

            # Create a legacy run bundle
            council_dir = council_logs_root(base, BRANCH)
            run_dir = council_dir / "run-abcd"
            run_dir.mkdir(parents=True)
            (run_dir / "claude.md").write_text("# claude\n\nSome response", encoding="utf-8")
            (run_dir / "metadata.json").write_text(
                '{"timestamp": "2026-01-01T00:00:00Z", "prompt": "test"}',
                encoding="utf-8",
            )

            result = runner.invoke(cli.app, ["council", "show", "run-abcd"])

            assert result.exit_code == 0
            assert "Legacy run" in result.output

    def test_show_not_found_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show", "nonexistent"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestCouncilList:
    def test_list_no_threads(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "No council threads" in result.output

    def test_list_shows_threads(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "Topic 1"])
                runner.invoke(cli.app, ["council", "ask", "--thread", "new", "Topic 2"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "council-" in result.output
            # Should show current thread marker
            assert "*" in result.output

    def test_list_shows_message_count(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query(responses):
                runner.invoke(cli.app, ["council", "ask", "A question"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "4 msgs" in result.output


class TestCouncilReset:
    def test_reset_clears_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "reset"])

            assert result.exit_code == 0
            assert "Sessions cleared" in result.output
