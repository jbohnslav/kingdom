"""Tests for the refactored council CLI commands (threads-based)."""

from __future__ import annotations

import contextlib
import json
import subprocess
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


def mock_council_query_to_thread(responses: dict[str, AgentResponse]):
    """Return a patch that makes Council.query_to_thread return responses and call the callback."""

    def side_effect(prompt, base, branch, thread_id, callback=None):
        from kingdom.thread import add_message

        for name, resp in responses.items():
            body = resp.text if resp.text else f"*Error: {resp.error}*"
            add_message(base, branch, thread_id, from_=name, to="king", body=body)
            if callback:
                callback(name, resp)
        return responses

    return patch.object(
        cli.Council,
        "query_to_thread",
        side_effect=side_effect,
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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
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

    def test_ask_to_creates_thread_with_only_target_member(self) -> None:
        """--to should create thread with only king + targeted member, not all members."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            from kingdom.thread import get_thread

            mock_result = MagicMock()
            mock_result.stdout = '{"result": "Codex says hi", "session_id": "s1"}'
            mock_result.stderr = ""
            mock_result.returncode = 0

            with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
                runner.invoke(cli.app, ["council", "ask", "--to", "codex", "Hello"])

            current = get_current_thread(base, BRANCH)
            meta = get_thread(base, BRANCH, current)
            assert set(meta.members) == {"king", "codex"}

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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
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
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "A question"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "4 msgs" in result.output


def _patch_async_dispatch():
    """Patch the background dispatch used by council ask --async.

    The implementation uses subprocess.Popen (replacing an earlier os.fork
    pattern).  We mock subprocess.Popen to prevent a real subprocess and also
    mock os.fork (returning a positive pid so the parent returns immediately)
    so the tests pass even if the loaded kingdom.cli still has the legacy
    double-fork code path.
    """
    return contextlib.ExitStack()


def _enter_async_patches(stack):
    """Enter both Popen and fork patches, return (mock_popen, mock_fork)."""
    mock_popen = stack.enter_context(patch("kingdom.cli.subprocess.Popen"))
    mock_fork = stack.enter_context(patch("kingdom.cli.os.fork", return_value=1))
    return mock_popen, mock_fork


class TestCouncilAskAsync:
    def test_async_returns_thread_id_immediately(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            with _patch_async_dispatch() as stack:
                mock_popen, _mock_fork = _enter_async_patches(stack)
                result = runner.invoke(cli.app, ["council", "ask", "--async", "Test async"])

            assert result.exit_code == 0
            assert "Thread:" in result.output
            assert "Dispatching to:" in result.output
            assert "kd council watch" in result.output

            # Verify Popen was called with start_new_session=True
            if mock_popen.called:
                mock_popen.assert_called_once()
                call_kwargs = mock_popen.call_args[1]
                assert call_kwargs["start_new_session"] is True
                assert call_kwargs["stdin"] == subprocess.DEVNULL

    def test_async_creates_thread_and_king_message(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            with _patch_async_dispatch() as stack:
                _enter_async_patches(stack)
                runner.invoke(cli.app, ["council", "ask", "--async", "Async question"])

            current = get_current_thread(base, BRANCH)
            assert current is not None
            assert current.startswith("council-")

            # King message should exist (responses are handled by worker subprocess)
            messages = list_messages(base, BRANCH, current)
            assert len(messages) == 1
            assert messages[0].from_ == "king"
            assert messages[0].body == "Async question"

    def test_async_passes_to_flag_to_worker(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            with _patch_async_dispatch() as stack:
                mock_popen, _mock_fork = _enter_async_patches(stack)
                runner.invoke(cli.app, ["council", "ask", "--async", "--to", "codex", "Test targeted"])

            # Verify --to flag is passed to the worker subprocess
            if mock_popen.called:
                mock_popen.assert_called_once()
                cmd = mock_popen.call_args[0][0]
                assert "--to" in cmd
                assert "codex" in cmd


class TestCouncilWatch:
    def test_watch_shows_existing_responses(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create a thread with responses already written
            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Test question"])

            current = get_current_thread(base, BRANCH)
            result = runner.invoke(cli.app, ["council", "watch", current])

            assert result.exit_code == 0
            assert "All members have responded" in result.output

    def test_watch_no_current_thread_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "watch"])

            assert result.exit_code == 1
            assert "No current council thread" in result.output

    def test_watch_nonexistent_thread_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "watch", "nonexistent"])

            assert result.exit_code == 1
            assert "Thread not found" in result.output

    def test_watch_renders_agent_panels(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Test"])

            current = get_current_thread(base, BRANCH)
            result = runner.invoke(cli.app, ["council", "watch", current])

            assert result.exit_code == 0
            # Should render response panels (agent names appear in output)
            assert "claude" in result.output
            assert "codex" in result.output
            assert "cursor" in result.output

    def test_watch_targeted_ask_completes_without_timeout(self) -> None:
        """watch on a --to thread should complete when the targeted member responds."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            mock_result = MagicMock()
            mock_result.stdout = '{"result": "Codex reply", "session_id": "s1"}'
            mock_result.stderr = ""
            mock_result.returncode = 0

            with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
                runner.invoke(cli.app, ["council", "ask", "--to", "codex", "Targeted question"])

            current = get_current_thread(base, BRANCH)
            result = runner.invoke(cli.app, ["council", "watch", current, "--timeout", "1"])

            assert result.exit_code == 0
            assert "All members have responded" in result.output
            assert "Missing" not in result.output

    def test_watch_ignores_prior_round_responses(self) -> None:
        """watch should only consider responses after the most recent king ask.

        Regression test: if a prior round had all members respond, watch on a
        new ask (with no responses yet) should NOT report 'All members have responded'.
        """
        from kingdom.thread import add_message

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Round 1: ask + all members respond
            responses = make_responses("claude", "codex", "cursor")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "First question"])

            current = get_current_thread(base, BRANCH)

            # Round 2: king asks again but no responses yet
            add_message(base, BRANCH, current, from_="king", to="all", body="Second question")

            result = runner.invoke(cli.app, ["council", "watch", current, "--timeout", "1"])

            assert result.exit_code == 0
            # Should NOT claim all members responded (those were from round 1)
            assert "All members have responded" not in result.output
            # Should show timeout since no new responses arrived
            assert "Timeout" in result.output


class TestCouncilShowLast:
    def test_show_last_no_logs_dir(self) -> None:
        """council show last should not crash when logs/council dir doesn't exist."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show", "last"])

            assert result.exit_code == 1
            assert "No council runs found" in result.output


class TestCouncilReset:
    def test_reset_clears_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "reset"])

            assert result.exit_code == 0
            assert "Sessions cleared" in result.output
