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
            add_message(base, branch, thread_id, from_=name, to="king", body=resp.thread_body())
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

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                result = runner.invoke(cli.app, ["council", "ask", "What is caching?"])

            assert result.exit_code == 0, result.output
            assert "Thread:" in result.output

            # Thread should have been created
            current = get_current_thread(base, BRANCH)
            assert current is not None
            assert current.startswith("council-")

            # Messages should exist: 1 king + 2 responses = 3
            messages = list_messages(base, BRANCH, current)
            assert len(messages) == 3
            assert messages[0].from_ == "king"
            assert messages[0].body == "What is caching?"

    def test_ask_continues_existing_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "First question"])
                result = runner.invoke(cli.app, ["council", "ask", "Follow up"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            # 2 king messages + 4 responses = 6
            assert len(messages) == 6
            assert messages[0].body == "First question"
            assert messages[3].body == "Follow up"

    def test_ask_thread_new_starts_fresh(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "First topic"])
                first_thread = get_current_thread(base, BRANCH)

                runner.invoke(cli.app, ["council", "ask", "--new-thread", "New topic"])
                second_thread = get_current_thread(base, BRANCH)

            assert first_thread != second_thread
            assert second_thread.startswith("council-")

            # Each thread should have 3 messages (1 king + 2 responses)
            assert len(list_messages(base, BRANCH, first_thread)) == 3
            assert len(list_messages(base, BRANCH, second_thread)) == 3

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

    def test_ask_stale_current_thread_recovers(self) -> None:
        """If current_thread points to a missing directory, ask creates a new thread."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Set a stale pointer
            set_current_thread(base, BRANCH, "council-gone")

            responses = make_responses("claude", "codex")
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

            responses = make_responses("claude", "codex")
            with mock_council_query(responses):
                result = runner.invoke(cli.app, ["council", "ask", "--json", "Test"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "thread_id" in data
            assert "responses" in data
            assert "claude" in data["responses"]

    def test_ask_does_not_modify_non_kd_files(self) -> None:
        """Council ask should not mutate project files outside .kd/."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            sentinel = base / "sentinel.py"
            original = "print('safe')\n"
            sentinel.write_text(original, encoding="utf-8")

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                result = runner.invoke(cli.app, ["council", "ask", "Analyze only"])

            assert result.exit_code == 0
            assert sentinel.read_text(encoding="utf-8") == original

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
            responses = make_responses("claude", "codex")
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

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Question 1"])
                thread_id = get_current_thread(base, BRANCH)

            result = runner.invoke(cli.app, ["council", "show", thread_id])

            assert result.exit_code == 0
            assert thread_id in result.output

    def test_show_defaults_to_most_recent_thread(self) -> None:
        """When current_thread is cleared, council show should fall back to the most recently created thread."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create two threads with explicit timestamps so ordering is deterministic
            create_thread(base, BRANCH, "council-old", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-old", from_="king", to="all", body="Old topic")
            add_message(base, BRANCH, "council-old", from_="claude", to="king", body="Old response")

            # Patch created_at on the second thread to be later
            create_thread(base, BRANCH, "council-new", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-new", from_="king", to="all", body="New topic")
            add_message(base, BRANCH, "council-new", from_="claude", to="king", body="New response")

            from kingdom.thread import threads_root

            new_meta = json.loads((threads_root(base, BRANCH) / "council-new" / "thread.json").read_text())
            new_meta["created_at"] = "2099-01-01T00:00:00Z"
            (threads_root(base, BRANCH) / "council-new" / "thread.json").write_text(json.dumps(new_meta))

            # Clear the current_thread pointer
            set_current_thread(base, BRANCH, None)

            result = runner.invoke(cli.app, ["council", "show"])

            assert result.exit_code == 0
            # Should show the most recently created thread, not the older one
            assert "council-new" in result.output
            assert "New topic" in result.output

    def test_show_no_threads_at_all_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show"])

            assert result.exit_code == 1

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
            assert "Archived session" in result.output

    def test_show_not_found_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show", "nonexistent"])

            assert result.exit_code == 1
            assert "not found" in result.output


def setup_multi_turn_thread(base: Path) -> str:
    """Create a thread with 3 turns for pagination tests. Returns thread ID."""
    from kingdom.thread import add_message, create_thread

    thread_id = "council-multi-turn"
    create_thread(base, BRANCH, thread_id, ["king", "claude", "codex"], "council")

    # Turn 1
    add_message(base, BRANCH, thread_id, from_="king", to="all", body="Question one?")
    add_message(base, BRANCH, thread_id, from_="claude", to="king", body="Answer 1 from claude")
    add_message(base, BRANCH, thread_id, from_="codex", to="king", body="Answer 1 from codex")

    # Turn 2
    add_message(base, BRANCH, thread_id, from_="king", to="all", body="Question two?")
    add_message(base, BRANCH, thread_id, from_="claude", to="king", body="Answer 2 from claude")
    add_message(base, BRANCH, thread_id, from_="codex", to="king", body="Answer 2 from codex")

    # Turn 3
    add_message(base, BRANCH, thread_id, from_="king", to="all", body="Question three?")
    add_message(base, BRANCH, thread_id, from_="claude", to="king", body="Answer 3 from claude")
    add_message(base, BRANCH, thread_id, from_="codex", to="king", body="Answer 3 from codex")

    return thread_id


class TestCouncilShowPagination:
    def test_default_shows_latest_turn_only(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            thread_id = setup_multi_turn_thread(base)

            result = runner.invoke(cli.app, ["council", "show", thread_id])

            assert result.exit_code == 0
            assert "Turn 3/3" in result.output
            assert "Question three?" in result.output
            assert "Answer 3 from claude" in result.output
            # Earlier turns should NOT appear
            assert "Question one?" not in result.output
            assert "Question two?" not in result.output

    def test_default_shows_hidden_summary(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            thread_id = setup_multi_turn_thread(base)

            result = runner.invoke(cli.app, ["council", "show", thread_id])

            assert result.exit_code == 0
            assert "1 turn of 3" in result.output
            assert "3 messages of 9" in result.output
            assert "--all" in result.output

    def test_last_n_shows_requested_turns(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            thread_id = setup_multi_turn_thread(base)

            result = runner.invoke(cli.app, ["council", "show", thread_id, "--last", "2"])

            assert result.exit_code == 0
            assert "Turn 2/3" in result.output
            assert "Turn 3/3" in result.output
            assert "Question two?" in result.output
            assert "Question three?" in result.output
            # Turn 1 should NOT appear
            assert "Question one?" not in result.output
            assert "2 turns of 3" in result.output

    def test_all_shows_every_turn(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            thread_id = setup_multi_turn_thread(base)

            result = runner.invoke(cli.app, ["council", "show", thread_id, "--all"])

            assert result.exit_code == 0
            assert "Turn 1/3" in result.output
            assert "Turn 2/3" in result.output
            assert "Turn 3/3" in result.output
            assert "Question one?" in result.output
            assert "Question two?" in result.output
            assert "Question three?" in result.output
            # No hidden summary when showing all
            assert "--all" not in result.output

    def test_single_turn_shows_no_hidden_summary(self) -> None:
        """A single-turn thread should show all messages with no 'Use --all' hint."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Single question"])

            result = runner.invoke(cli.app, ["council", "show"])

            assert result.exit_code == 0
            assert "Turn 1/1" in result.output
            assert "--all" not in result.output

    def test_turn_header_shows_timestamp(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            thread_id = setup_multi_turn_thread(base)

            result = runner.invoke(cli.app, ["council", "show", thread_id])

            assert result.exit_code == 0
            # Turn header includes a timestamp pattern (YYYY-MM-DD HH:MM:SS)
            import re

            assert re.search(r"Turn 3/3.*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result.output)

    def test_last_n_clamped_to_total(self) -> None:
        """--last 100 on a 3-turn thread shows all 3 turns."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            thread_id = setup_multi_turn_thread(base)

            result = runner.invoke(cli.app, ["council", "show", thread_id, "--last", "100"])

            assert result.exit_code == 0
            assert "Turn 1/3" in result.output
            assert "Turn 3/3" in result.output
            # No hidden summary — all turns visible
            assert "--all" not in result.output


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

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Topic 1"])
                runner.invoke(cli.app, ["council", "ask", "--new-thread", "Topic 2"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "council-" in result.output
            # Should show current thread marker
            assert "*" in result.output

    def test_list_shows_topic_summary(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Should we use Redis or Memcached?"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "Should we use Redis or Memcached?" in result.output

    def test_list_shows_member_status(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "A question"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            # All members responded — should show check marks
            assert "claude" in result.output
            assert "codex" in result.output

    def test_list_shows_mixed_member_states(self) -> None:
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-mixed", ["king", "claude", "codex"], "council")
            add_message(base, BRANCH, "council-mixed", from_="king", to="all", body="Question?")
            add_message(base, BRANCH, "council-mixed", from_="claude", to="king", body="Good answer")
            # codex has not responded — pending

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "claude" in result.output
            assert "codex" in result.output

    def test_list_shows_errored_member(self) -> None:
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-err", ["king", "claude", "codex"], "council")
            add_message(base, BRANCH, "council-err", from_="king", to="all", body="Question?")
            add_message(base, BRANCH, "council-err", from_="claude", to="king", body="Good answer")
            add_message(base, BRANCH, "council-err", from_="codex", to="king", body="*Error: Exit code 1*")

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "claude" in result.output
            assert "codex" in result.output

    def test_list_shows_legend(self) -> None:
        """council list should print a legend explaining status symbols."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "A question"])

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "responded" in result.output
            assert "running" in result.output
            assert "errored" in result.output
            assert "timed out" in result.output
            assert "pending" in result.output

    def test_list_no_legend_when_no_threads(self) -> None:
        """When there are no council threads, no legend should be printed."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "No council threads" in result.output
            assert "responded" not in result.output


def patch_async_dispatch():
    """Patch the background dispatch used by council ask (default async mode).

    Mocks subprocess.Popen to prevent a real worker subprocess from launching.
    """
    return contextlib.ExitStack()


def enter_async_patches(stack):
    """Enter Popen patch, return mock_popen."""
    mock_popen = stack.enter_context(patch("kingdom.cli.subprocess.Popen"))
    return mock_popen


class TestCouncilAskAsync:
    def test_no_watch_returns_immediately(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            with patch_async_dispatch() as stack:
                mock_popen = enter_async_patches(stack)
                result = runner.invoke(cli.app, ["council", "ask", "--async", "--no-watch", "Test async"])

            assert result.exit_code == 0
            assert "Dispatched" in result.output

            # Verify Popen was called with start_new_session=True
            mock_popen.assert_called_once()
            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs["start_new_session"] is True
            assert call_kwargs["stdin"] == subprocess.DEVNULL

    def test_no_watch_creates_thread_and_king_message(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            with patch_async_dispatch() as stack:
                enter_async_patches(stack)
                runner.invoke(cli.app, ["council", "ask", "--async", "--no-watch", "Async question"])

            current = get_current_thread(base, BRANCH)
            assert current is not None
            assert current.startswith("council-")

            # King message should exist (responses are handled by worker subprocess)
            messages = list_messages(base, BRANCH, current)
            assert len(messages) == 1
            assert messages[0].from_ == "king"
            assert messages[0].body == "Async question"

    def test_no_watch_passes_to_flag_to_worker(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            with patch_async_dispatch() as stack:
                mock_popen = enter_async_patches(stack)
                runner.invoke(cli.app, ["council", "ask", "--async", "--no-watch", "--to", "codex", "Test targeted"])

            # Verify --to flag is passed to the worker subprocess
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
            responses = make_responses("claude", "codex")
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
            assert "No council threads" in result.output

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

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Test"])

            current = get_current_thread(base, BRANCH)
            result = runner.invoke(cli.app, ["council", "watch", current])

            assert result.exit_code == 0
            # Should render response panels (agent names appear in output)
            assert "claude" in result.output
            assert "codex" in result.output

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
            responses = make_responses("claude", "codex")
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
            assert "No council history found" in result.output


class TestCouncilMentions:
    def test_single_mention_targets_member(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            mock_result = MagicMock()
            mock_result.stdout = '{"result": "Codex reply", "session_id": "s1"}'
            mock_result.stderr = ""
            mock_result.returncode = 0

            with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
                result = runner.invoke(cli.app, ["council", "ask", "@codex what do you think?"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            # 1 king + 1 codex = 2
            assert len(messages) == 2
            assert messages[1].from_ == "codex"

    def test_multiple_mentions_filters_council(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                result = runner.invoke(cli.app, ["council", "ask", "@claude @codex thoughts?"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            # 1 king + 2 responses = 3
            assert len(messages) == 3
            names = {m.from_ for m in messages if m.from_ != "king"}
            assert names == {"claude", "codex"}

    def test_at_all_queries_everyone(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                result = runner.invoke(cli.app, ["council", "ask", "@all what do you think?"])

            assert result.exit_code == 0

            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            assert len(messages) == 3  # king + 2 responses

    def test_unknown_mention_fails(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "ask", "@nobody what?"])

            assert result.exit_code == 1
            assert "Unknown @mention" in result.output

    def test_to_flag_overrides_mentions(self) -> None:
        """--to flag takes precedence over @mentions in prompt."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            mock_result = MagicMock()
            mock_result.stdout = '{"result": "Claude reply", "session_id": "s1"}'
            mock_result.stderr = ""
            mock_result.returncode = 0

            with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
                result = runner.invoke(cli.app, ["council", "ask", "--to", "claude", "@codex what?"])

            assert result.exit_code == 0
            current = get_current_thread(base, BRANCH)
            messages = list_messages(base, BRANCH, current)
            assert messages[1].from_ == "claude"


class TestCouncilStatus:
    def test_status_shows_all_responded(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Test question"])

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "complete" in result.output
            assert "claude: responded" in result.output
            assert "codex: responded" in result.output

    def test_status_shows_pending_members(self) -> None:
        """When some members haven't responded, status shows them as pending."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create thread manually with only one response
            create_thread(base, BRANCH, "council-test", ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, "council-test")
            add_message(base, BRANCH, "council-test", from_="king", to="all", body="Question")
            add_message(base, BRANCH, "council-test", from_="claude", to="king", body="My answer")

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "waiting" in result.output
            assert "claude: responded" in result.output
            assert "codex: pending" in result.output

    def test_status_specific_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Test"])

            thread_id = get_current_thread(base, BRANCH)
            result = runner.invoke(cli.app, ["council", "status", thread_id])

            assert result.exit_code == 0
            assert thread_id in result.output

    def test_status_all_threads(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Topic 1"])
                runner.invoke(cli.app, ["council", "ask", "--new-thread", "Topic 2"])

            result = runner.invoke(cli.app, ["council", "status", "--all"])

            assert result.exit_code == 0
            # Should show status for both threads
            assert result.output.count("complete") == 2

    def test_status_verbose_shows_log_paths(self) -> None:
        """--verbose flag shows log file paths for each member."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-test", ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, "council-test")
            add_message(base, BRANCH, "council-test", from_="king", to="all", body="Q")
            add_message(base, BRANCH, "council-test", from_="claude", to="king", body="A")

            # Create a log file for claude
            from kingdom.state import logs_root

            log_dir = logs_root(base, BRANCH)
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "council-claude.log").write_text("some log output")

            result = runner.invoke(cli.app, ["council", "status", "--verbose"])

            assert result.exit_code == 0
            assert "thread:" in result.output
            assert "council-test" in result.output
            assert "council-claude.log" in result.output
            # codex has no log — log path only shown when file exists
            assert "council-codex.log" not in result.output

    def test_status_no_threads_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 1

    def test_status_falls_back_to_most_recent(self) -> None:
        """When current_thread is unset, status uses most recent thread."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-old", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-old", from_="king", to="all", body="Old")
            add_message(base, BRANCH, "council-old", from_="claude", to="king", body="Reply")

            create_thread(base, BRANCH, "council-recent", ["king", "codex"], "council")
            add_message(base, BRANCH, "council-recent", from_="king", to="all", body="New")

            # Ensure council-recent sorts last
            import json

            from kingdom.thread import threads_root

            meta_path = threads_root(base, BRANCH) / "council-recent" / "thread.json"
            meta = json.loads(meta_path.read_text())
            meta["created_at"] = "2099-01-01T00:00:00Z"
            meta_path.write_text(json.dumps(meta))

            set_current_thread(base, BRANCH, None)

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "council-recent" in result.output
            assert "codex: pending" in result.output

    def test_status_shows_errored_member(self) -> None:
        """Status should show 'errored' for members that responded with an error."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-err", ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, "council-err")
            add_message(base, BRANCH, "council-err", from_="king", to="all", body="Q")
            add_message(base, BRANCH, "council-err", from_="claude", to="king", body="Good")
            add_message(base, BRANCH, "council-err", from_="codex", to="king", body="*Error: Exit code 1*")

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "errors" in result.output
            assert "claude: responded" in result.output
            assert "codex: errored" in result.output

    def test_status_shows_timed_out_member(self) -> None:
        """Status should show 'timed out' for members that timed out."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-to", ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, "council-to")
            add_message(base, BRANCH, "council-to", from_="king", to="all", body="Q")
            add_message(base, BRANCH, "council-to", from_="claude", to="king", body="Good")
            add_message(base, BRANCH, "council-to", from_="codex", to="king", body="*Error: Timeout after 600s*")

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "claude: responded" in result.output
            assert "codex: timed out" in result.output

    def test_status_shows_running_member(self) -> None:
        """Status should show 'running' for members with active stream files."""
        from kingdom.thread import add_message, create_thread, thread_dir

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-run", ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, "council-run")
            add_message(base, BRANCH, "council-run", from_="king", to="all", body="Q")

            # Simulate active stream file for claude
            tdir = thread_dir(base, BRANCH, "council-run")
            (tdir / ".stream-claude.jsonl").write_text('{"type":"event"}\n')

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "running" in result.output
            assert "claude: running" in result.output
            assert "codex: pending" in result.output


class TestCouncilReset:
    def test_reset_clears_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "reset"])

            assert result.exit_code == 0
            assert "sessions cleared" in result.output.lower()

    def test_reset_single_member(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "reset", "--member", "claude"])

            assert result.exit_code == 0
            assert "claude" in result.output.lower()
            assert "cleared" in result.output.lower()

    def test_reset_unknown_member(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "reset", "--member", "nonexistent"])

            assert result.exit_code == 1
            assert "Unknown member" in result.output


class TestCouncilRetry:
    def test_retry_no_thread(self) -> None:
        """Retry with no current thread should error."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "retry"])

            assert result.exit_code == 1
            assert "No council threads" in result.output

    def test_retry_all_ok(self) -> None:
        """Retry when all members responded successfully should say nothing to retry."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            thread_id = "council-retry-test"
            create_thread(base, BRANCH, thread_id, ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, thread_id)
            add_message(base, BRANCH, thread_id, from_="king", to="all", body="test question")
            add_message(base, BRANCH, thread_id, from_="claude", to="king", body="Good response")
            add_message(base, BRANCH, thread_id, from_="codex", to="king", body="Also good")

            result = runner.invoke(cli.app, ["council", "retry"])

            assert result.exit_code == 0
            assert "Nothing to retry" in result.output

    def test_retry_failed_members(self) -> None:
        """Retry should re-query members that failed."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            thread_id = "council-retry-fail"
            create_thread(base, BRANCH, thread_id, ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, thread_id)
            add_message(base, BRANCH, thread_id, from_="king", to="all", body="test question")
            add_message(base, BRANCH, thread_id, from_="claude", to="king", body="Good response")
            add_message(base, BRANCH, thread_id, from_="codex", to="king", body="*Error: Timeout after 600s*")

            # Mock query_to_thread to handle the retry
            retry_responses = {
                "codex": AgentResponse(name="codex", text="Recovered response", elapsed=5.0),
            }
            with mock_council_query_to_thread(retry_responses):
                result = runner.invoke(cli.app, ["council", "retry"])

            assert result.exit_code == 0
            assert "codex" in result.output

    def test_retry_missing_members(self) -> None:
        """Retry should re-query members that never responded."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            thread_id = "council-retry-miss"
            create_thread(base, BRANCH, thread_id, ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, thread_id)
            add_message(base, BRANCH, thread_id, from_="king", to="all", body="test question")
            add_message(base, BRANCH, thread_id, from_="claude", to="king", body="Good response")
            # codex never responded

            retry_responses = {
                "codex": AgentResponse(name="codex", text="Late response", elapsed=5.0),
            }
            with mock_council_query_to_thread(retry_responses):
                result = runner.invoke(cli.app, ["council", "retry"])

            assert result.exit_code == 0
            assert "codex" in result.output.lower()

    def test_retry_respects_targeted_ask(self) -> None:
        """Retry after --to codex should only retry codex, not other members."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Thread has all members, but last ask was targeted to codex only
            thread_id = "council-retry-target"
            create_thread(base, BRANCH, thread_id, ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, thread_id)
            add_message(base, BRANCH, thread_id, from_="king", to="codex", body="targeted question")
            add_message(base, BRANCH, thread_id, from_="codex", to="king", body="*Error: Timeout after 600s*")

            retry_responses = {
                "codex": AgentResponse(name="codex", text="Recovered", elapsed=5.0),
            }
            with mock_council_query_to_thread(retry_responses):
                result = runner.invoke(cli.app, ["council", "retry"])

            assert result.exit_code == 0
            # Should only retry codex, not claude
            assert "Retrying: codex" in result.output


class TestNoResultsMessages:
    """Tests for helpful empty-state messages with next-step guidance."""

    def test_council_list_empty_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "list"])

            assert result.exit_code == 0
            assert "No council threads" in result.output
            assert "kd council ask" in result.output

    def test_council_status_all_empty_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "status", "--all"])

            assert result.exit_code == 0
            assert "No council threads" in result.output
            assert "kd council ask" in result.output

    def test_council_show_last_empty_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show", "last"])

            assert result.exit_code == 1
            assert "No council history found" in result.output
            assert "kd council ask" in result.output

    def test_council_show_thread_no_messages_shows_guidance(self) -> None:
        from kingdom.thread import create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-empty", ["king", "claude"], "council")

            result = runner.invoke(cli.app, ["council", "show", "council-empty"])

            assert result.exit_code == 1
            assert "no messages" in result.output
            assert "kd council ask" in result.output


class TestCouncilThreadResolution:
    """Tests for the unified resolve_council_thread_id helper."""

    def test_show_prefix_match(self) -> None:
        """council show with a prefix should resolve to the full thread ID."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-ab12", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-ab12", from_="king", to="all", body="Hello")
            add_message(base, BRANCH, "council-ab12", from_="claude", to="king", body="Hi")

            result = runner.invoke(cli.app, ["council", "show", "council-ab"])

            assert result.exit_code == 0
            assert "council-ab12" in result.output

    def test_status_prefix_match(self) -> None:
        """council status with a prefix should resolve to the full thread ID."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-cd34", ["king", "claude"], "council")
            set_current_thread(base, BRANCH, "council-cd34")
            add_message(base, BRANCH, "council-cd34", from_="king", to="all", body="Q")
            add_message(base, BRANCH, "council-cd34", from_="claude", to="king", body="A")

            result = runner.invoke(cli.app, ["council", "status", "council-cd"])

            assert result.exit_code == 0
            assert "council-cd34" in result.output

    def test_show_ambiguous_prefix(self) -> None:
        """Ambiguous prefix should list matching threads."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-ab01", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-ab01", from_="king", to="all", body="Topic one")

            create_thread(base, BRANCH, "council-ab02", ["king", "codex"], "council")
            add_message(base, BRANCH, "council-ab02", from_="king", to="all", body="Topic two")

            result = runner.invoke(cli.app, ["council", "show", "council-ab"])

            assert result.exit_code == 1
            assert "matches multiple threads" in result.output
            assert "council-ab01" in result.output
            assert "council-ab02" in result.output
            assert "Topic one" in result.output
            assert "Topic two" in result.output

    def test_show_not_found_lists_available(self) -> None:
        """Thread not found should list available threads with topics."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-ab12", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-ab12", from_="king", to="all", body="Known topic")

            result = runner.invoke(cli.app, ["council", "show", "council-zzzz"])

            assert result.exit_code == 1
            assert "Thread not found: council-zzzz" in result.output
            assert "Available council threads" in result.output
            assert "council-ab12" in result.output
            assert "Known topic" in result.output

    def test_show_not_found_no_threads(self) -> None:
        """Thread not found with no threads should say to create one."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["council", "show", "council-zzzz"])

            assert result.exit_code == 1
            assert "Thread not found" in result.output
            assert "kd council ask" in result.output

    def test_fallback_to_most_recent_prints_thread_id(self) -> None:
        """When falling back to most recent thread, print which thread was selected."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-first", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-first", from_="king", to="all", body="First")
            add_message(base, BRANCH, "council-first", from_="claude", to="king", body="Reply")

            # Clear the current thread pointer
            set_current_thread(base, BRANCH, None)

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "Using most recent thread: council-first" in result.output

    def test_stale_pointer_falls_back(self) -> None:
        """A stale current_thread pointer should fall back to most recent."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-real", ["king", "claude"], "council")
            add_message(base, BRANCH, "council-real", from_="king", to="all", body="Question")
            add_message(base, BRANCH, "council-real", from_="claude", to="king", body="Answer")

            # Set a stale pointer
            set_current_thread(base, BRANCH, "council-deleted")

            result = runner.invoke(cli.app, ["council", "status"])

            assert result.exit_code == 0
            assert "Using most recent thread: council-real" in result.output

    def test_watch_prefix_match(self) -> None:
        """council watch with prefix should resolve correctly."""

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            responses = make_responses("claude", "codex")
            with mock_council_query_to_thread(responses):
                runner.invoke(cli.app, ["council", "ask", "Test question"])

            current = get_current_thread(base, BRANCH)
            # Use just the first characters as prefix
            prefix = current[:10]

            result = runner.invoke(cli.app, ["council", "watch", prefix])

            assert result.exit_code == 0
            assert "All members have responded" in result.output

    def test_retry_prefix_match(self) -> None:
        """council retry with prefix should resolve correctly."""
        from kingdom.thread import add_message, create_thread

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            create_thread(base, BRANCH, "council-ef56", ["king", "claude", "codex"], "council")
            set_current_thread(base, BRANCH, "council-ef56")
            add_message(base, BRANCH, "council-ef56", from_="king", to="all", body="test question")
            add_message(base, BRANCH, "council-ef56", from_="claude", to="king", body="Good response")
            add_message(base, BRANCH, "council-ef56", from_="codex", to="king", body="Also good")

            result = runner.invoke(cli.app, ["council", "retry", "council-ef"])

            assert result.exit_code == 0
            assert "Nothing to retry" in result.output
