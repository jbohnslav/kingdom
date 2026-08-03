"""Tests for kd tk log (worklog) commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.ticket import ticket_app
from kingdom.state import (
    branch_root,
    execution_context_path,
    record_execution_ticket_context,
    resolve_execution_context,
)
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


def create_ticket_in(directory: Path, ticket_id: str = "kin-t001") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ticket = Ticket(
        id=ticket_id,
        status="open",
        title="Test ticket",
        body="Body text",
        created=datetime.now(UTC),
    )
    path = directory / f"{ticket_id}.md"
    write_ticket(ticket, path)
    return path


class TestTicketLog:
    def test_log_appends_worklog_entry(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg01")

        result = runner.invoke(ticket_app, ["log", "kin-lg01", "Started working on this"])

        assert result.exit_code == 0, result.output
        assert "kin-lg01" in result.output
        assert "Started working on this" in result.output

        # Verify the file was updated
        content = (tickets_dir / "kin-lg01.md").read_text()
        assert "## Worklog" in content
        assert "Started working on this" in content

    def test_log_multiple_entries(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg02")

        runner.invoke(ticket_app, ["log", "kin-lg02", "First entry"])
        result = runner.invoke(ticket_app, ["log", "kin-lg02", "Second entry"])

        assert result.exit_code == 0, result.output

        content = (tickets_dir / "kin-lg02.md").read_text()
        assert "First entry" in content
        assert "Second entry" in content

        # Order matters: first before second
        first_pos = content.index("First entry")
        second_pos = content.index("Second entry")
        assert first_pos < second_pos

    def test_log_not_found(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["log", "kin-nope", "message"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_log_preserves_ticket_content(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(
            id="kin-lg03",
            status="open",
            title="Preserve content",
            body="## Acceptance Criteria\n\n- [ ] Item 1\n- [ ] Item 2",
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "kin-lg03.md")

        result = runner.invoke(ticket_app, ["log", "kin-lg03", "Did some work"])

        assert result.exit_code == 0, result.output

        content = (tickets_dir / "kin-lg03.md").read_text()
        assert "# Preserve content" in content
        assert "## Acceptance Criteria" in content
        assert "- [ ] Item 1" in content
        assert "- [ ] Item 2" in content
        assert "Did some work" in content

    def test_log_missing_message_errors(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg04")

        result = runner.invoke(ticket_app, ["log", "kin-lg04"])

        assert result.exit_code == 1
        assert "No worklog message provided." in result.output

    def test_log_reads_multiline_special_characters_from_stdin(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg05")
        message = 'First line\n"quotes" & <angles> $HOME `ticks` * [literal]\n'

        result = runner.invoke(ticket_app, ["log", "kin-lg05"], input=message)

        assert result.exit_code == 0, result.output
        content = (tickets_dir / "kin-lg05.md").read_text()
        assert "— First line" in content
        assert '  "quotes" & <angles> $HOME `ticks` * [literal]' in content

    def test_log_records_agent_attribution(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg06")

        result = runner.invoke(
            ticket_app,
            ["log", "kin-lg06", "Attributed entry"],
            env={"KD_AGENT_NAME": "peasant-3af0"},
        )

        assert result.exit_code == 0, result.output
        content = (tickets_dir / "kin-lg06.md").read_text()
        assert "[peasant-3af0] — Attributed entry" in content

    def test_log_refreshes_only_the_exact_owner_context(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(tickets_dir, "kin-lg07")
        stale_time = datetime.now(UTC) - timedelta(days=2)

        owner = resolve_execution_context(session_id="owner", host="codex", now=stale_time, cwd=cli_project)
        foreign = resolve_execution_context(session_id="foreign", host="codex", now=stale_time, cwd=cli_project)
        assert owner is not None
        assert foreign is not None
        record_execution_ticket_context(cli_project, owner, "kin-lg07", feature=BRANCH)
        ticket = Ticket(
            id="kin-lg07",
            status="in_progress",
            title="Test ticket",
            assignee=owner.context_id,
            created=datetime.now(UTC),
        )
        write_ticket(ticket, ticket_path)

        foreign_result = runner.invoke(
            ticket_app,
            ["log", "kin-lg07", "Foreign review"],
            env={"KD_CONTEXT": "foreign", "KD_HOST": "codex"},
        )
        assert foreign_result.exit_code == 0, foreign_result.output
        owner_path = execution_context_path(cli_project, owner)
        assert json.loads(owner_path.read_text())["last_seen"] == stale_time.isoformat()
        assert not execution_context_path(cli_project, foreign).exists()

        owner_result = runner.invoke(
            ticket_app,
            ["log", "kin-lg07", "Owner progress"],
            env={"KD_CONTEXT": "owner", "KD_HOST": "codex"},
        )
        assert owner_result.exit_code == 0, owner_result.output
        assert datetime.fromisoformat(json.loads(owner_path.read_text())["last_seen"]) > stale_time

    def test_owner_log_keeps_context_live_in_status(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(tickets_dir, "kin-lg08")
        stale_time = datetime.now(UTC) - timedelta(days=2)
        owner = resolve_execution_context(session_id="owner", host="codex", now=stale_time, cwd=cli_project)
        assert owner is not None
        record_execution_ticket_context(cli_project, owner, "kin-lg08", feature=BRANCH)
        ticket = Ticket(
            id="kin-lg08",
            status="in_progress",
            title="Test ticket",
            assignee=owner.context_id,
            created=datetime.now(UTC),
        )
        write_ticket(ticket, ticket_path)

        log_result = runner.invoke(
            ticket_app,
            ["log", "kin-lg08", "Still working"],
            env={"KD_CONTEXT": "owner", "KD_HOST": "codex"},
        )
        assert log_result.exit_code == 0, log_result.output

        status_result = runner.invoke(app, ["status", "--json", "--stale-hours", "0.01"])
        assert status_result.exit_code == 0, status_result.output
        contexts = {item["context_id"]: item for item in json.loads(status_result.output)["contexts"]}
        assert contexts[owner.context_id]["stale"] is False

    def test_primary_help_only_lists_log(self) -> None:
        result = runner.invoke(ticket_app, ["--help"])

        assert result.exit_code == 0, result.output
        assert "add-note" not in result.output
        assert "Append a worklog entry to a ticket." in result.output

    def test_log_help_routes_command_rich_messages_to_stdin(self) -> None:
        result = runner.invoke(ticket_app, ["log", "--help"])

        assert result.exit_code == 0, result.output
        help_text = " ".join(result.output.split())
        assert "Plain-text-only inline message" in help_text
        assert "command-rich or multiline text safely from" in help_text
        assert "stdin." in help_text
