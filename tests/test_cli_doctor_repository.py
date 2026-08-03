from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.helpers import bundled_skill_files, write_skill_bundle
from kingdom.cli.plugin import HOOK_CONFIG, HOOK_EVENTS
from kingdom.codex_plugin import install_codex_plugin
from kingdom.doctor import claude_install_issues, codex_install_issues, skill_install_issues
from kingdom.state import branch_root, ensure_branch_layout, write_json
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "repository_upgrade" / "v0_6_mixed"


def tree_snapshot(base: Path) -> dict[str, bytes]:
    return {str(path.relative_to(base)): path.read_bytes() for path in sorted(base.glob("**/*")) if path.is_file()}


def write_context(
    base: Path,
    name: str,
    ticket_id: str,
    *,
    active: bool = True,
    role: str = "agent",
    parent_agent_id: str | None = None,
) -> None:
    path = base / ".kd" / "runtime" / "contexts" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "context_id": f"codex:{name}",
                "host": "codex",
                "role": role,
                "session_id": name,
                "parent_agent_id": parent_agent_id,
                "cwd": str(base),
                "source": "hook",
                "ticket_id": ticket_id,
                "feature": "feature-upgrade",
                "location": "branch:feature-upgrade",
                "last_seen": "2026-08-03T12:00:00+00:00",
                "active": active,
            }
        ),
        encoding="utf-8",
    )


def test_doctor_reports_repository_and_host_drift_without_writing(tmp_path: Path) -> None:
    base = tmp_path / "repository"
    home = tmp_path / "home"
    shutil.copytree(FIXTURE, base)
    tickets_dir = branch_root(base, "feature-upgrade") / "tickets"
    write_ticket(
        Ticket(id="active2", status="in_progress", title="Second legacy ticket", assignee="hand"),
        tickets_dir / "active2.md",
    )
    bad_resolution = base / ".kd" / "backlog" / "tickets" / "bad1.md"
    bad_resolution.write_text(
        '---\nid: "bad1"\nstatus: closed\ndeps: []\nlinks: []\n'
        "created: 2026-07-01T12:00:00Z\ntype: task\npriority: 2\n"
        "resolution: abandoned\n---\n# Bad resolution\n",
        encoding="utf-8",
    )
    (tickets_dir / "broken.md").write_text("---\nid: broken\n", encoding="utf-8")
    write_context(base, "orphan", "missing1")
    legacy_orphan = base / ".kd" / "runtime" / "terminal-context" / "orphan.json"
    legacy_orphan.write_text(
        json.dumps(
            {
                "ticket_id": "missing2",
                "feature": "feature-upgrade",
                "location": "branch:feature-upgrade",
                "updated_at": "2026-08-03T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    settings_path = base / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"hooks": {event: [HOOK_CONFIG] for event in HOOK_EVENTS}}),
        encoding="utf-8",
    )
    install_codex_plugin(home)
    codex_hooks = home / "plugins" / "kingdom" / "hooks" / "hooks.json"
    codex_hooks.write_text("{}\n", encoding="utf-8")
    before = tree_snapshot(tmp_path)

    with (
        patch("kingdom.state.Path.cwd", return_value=base),
        patch("kingdom.cli.Path.home", return_value=home),
        patch("kingdom.cli.check_cli", return_value=(True, None)),
    ):
        human = runner.invoke(app, ["doctor"])
        machine = runner.invoke(app, ["doctor", "--json"])

    assert human.exit_code == 1
    assert machine.exit_code == 1
    report = json.loads(machine.output)
    assert set(report) >= {
        "config",
        "agents",
        "bindings",
        "contexts",
        "tickets",
        "resolutions",
        "host_installs",
    }
    assert {issue["code"] for issue in report["bindings"]} >= {"binding.ambiguous"}
    assert {issue["code"] for issue in report["contexts"]} >= {
        "context.invalid",
        "context.orphan",
    }
    assert {issue["code"] for issue in report["tickets"]} >= {"ticket.invalid"}
    assert {issue["code"] for issue in report["resolutions"]} >= {"ticket.resolution.invalid"}
    assert {issue["code"] for issue in report["host_installs"]} >= {
        "host.claude.hooks_legacy",
        "host.codex.plugin_modified",
    }
    repairs = "\n".join(
        issue["repair"]
        for section in ("bindings", "contexts", "tickets", "resolutions", "host_installs")
        for issue in report[section]
    )
    assert "kd tk start <id>" in repairs
    assert "kd tk reopen bad1" in repairs
    assert "kd plugin enable" in repairs
    assert "kd plugin install codex" in repairs
    assert "mv -n" in repairs
    assert "Back up and review" in repairs
    assert "Doctor is read-only; no files were changed." in human.output
    assert tree_snapshot(tmp_path) == before


def test_check_cli_rejects_nonzero_version_command() -> None:
    from kingdom.cli.config import check_cli

    installed, error = check_cli(["/usr/bin/false"])

    assert installed is False
    assert error == "Command exited with status 1"


def test_check_cli_reports_non_executable_command(tmp_path: Path) -> None:
    from kingdom.cli.config import check_cli

    command = tmp_path / "agent-cli"
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o644)

    installed, error = check_cli([str(command)])

    assert installed is False
    assert error is not None
    assert "Could not run command" in error


def test_doctor_reports_structurally_invalid_claude_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"hooks": []}', encoding="utf-8")

    issues = claude_install_issues(tmp_path)

    assert [issue.code for issue in issues] == ["host.claude.settings_invalid"]
    assert "kd plugin enable" in issues[0].repair


def test_doctor_detects_known_legacy_claude_hook_command(tmp_path: Path) -> None:
    legacy_hook = {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/kd-workflow.sh',
                "timeout": 10,
            }
        ],
    }
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps({"hooks": {event: [legacy_hook] for event in HOOK_EVENTS}}),
        encoding="utf-8",
    )

    issues = claude_install_issues(tmp_path)

    assert [issue.code for issue in issues] == ["host.claude.hooks_legacy"]
    assert issues[0].repair == "Run `kd plugin enable` to replace legacy hooks and add current lifecycle coverage."


def test_doctor_ignores_inactive_context_with_historical_ticket_id(tmp_path: Path) -> None:
    from kingdom.doctor import context_issues

    write_context(tmp_path, "finished", "missing1", active=False)

    assert context_issues(tmp_path) == []


def test_doctor_allows_parent_subagent_sharing_but_flags_unrelated_owner(tmp_path: Path) -> None:
    from kingdom.doctor import context_issues

    tickets = ensure_branch_layout(tmp_path, "feature-upgrade") / "tickets"
    write_ticket(
        Ticket(id="work1", status="in_progress", title="Shared work", assignee="codex:parent"),
        tickets / "work1.md",
    )
    write_context(
        tmp_path,
        "child",
        "work1",
        role="subagent",
        parent_agent_id="codex:parent",
    )
    write_context(tmp_path, "other", "work1")

    issues = context_issues(tmp_path)

    assert [issue.code for issue in issues] == ["binding.mismatch"]
    assert issues[0].path == ".kd/runtime/contexts/other.json"
    assert "kd tk start" not in issues[0].repair
    assert "mv -n" in issues[0].repair


def test_doctor_detects_one_exact_context_assigned_to_multiple_tickets(tmp_path: Path) -> None:
    from kingdom.doctor import binding_issues

    tickets = ensure_branch_layout(tmp_path, "feature-upgrade") / "tickets"
    for ticket_id in ("one1", "two2"):
        write_ticket(
            Ticket(id=ticket_id, status="in_progress", title=ticket_id, assignee="codex:shared"),
            tickets / f"{ticket_id}.md",
        )
    write_context(tmp_path, "shared", "one1")

    issues = binding_issues(tmp_path)

    assert [issue.code for issue in issues] == ["binding.exact_ambiguous"]
    assert "one1" in issues[0].message
    assert "two2" in issues[0].message


def test_doctor_detects_exact_context_conflicts_across_branches(tmp_path: Path) -> None:
    from kingdom.doctor import binding_issues

    for branch, ticket_id in (("feature-one", "one1"), ("feature-two", "two2")):
        tickets = ensure_branch_layout(tmp_path, branch) / "tickets"
        write_ticket(
            Ticket(id=ticket_id, status="in_progress", title=ticket_id, assignee="codex:shared"),
            tickets / f"{ticket_id}.md",
        )

    issues = binding_issues(tmp_path)

    assert [issue.code for issue in issues] == ["binding.exact_ambiguous"]
    assert "one1" in issues[0].message
    assert "two2" in issues[0].message


def test_doctor_distinguishes_context_location_drift_from_missing_ticket(tmp_path: Path) -> None:
    from kingdom.doctor import context_issues

    tickets = ensure_branch_layout(tmp_path, "feature-upgrade") / "tickets"
    write_ticket(
        Ticket(id="work1", status="in_progress", title="Moved", assignee="codex:moved"),
        tickets / "work1.md",
    )
    write_context(tmp_path, "moved", "work1")
    context_path = tmp_path / ".kd" / "runtime" / "contexts" / "moved.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["location"] = "backlog"
    write_json(context_path, context)

    issues = context_issues(tmp_path)

    assert [issue.code for issue in issues] == ["binding.location_mismatch"]
    assert "kd tk start work1" in issues[0].repair


def test_doctor_reports_context_ticket_file_with_wrong_frontmatter_id(tmp_path: Path) -> None:
    from kingdom.doctor import context_issues

    tickets = ensure_branch_layout(tmp_path, "feature-upgrade") / "tickets"
    write_ticket(
        Ticket(id="other1", status="in_progress", title="Wrong ID", assignee="codex:mismatch"),
        tickets / "expected1.md",
    )
    write_context(tmp_path, "mismatch", "expected1")

    issues = context_issues(tmp_path)

    assert [issue.code for issue in issues] == ["context.orphan"]
    assert "expected1" in issues[0].message


def test_doctor_rejects_missing_and_self_resolution_targets(tmp_path: Path) -> None:
    from kingdom.doctor import resolution_issues

    tickets = ensure_branch_layout(tmp_path, "feature-upgrade") / "tickets"
    write_ticket(
        Ticket(
            id="gone1",
            status="closed",
            title="Missing target",
            resolution="duplicate",
            close_reason="Duplicate",
            duplicate_of="missing1",
        ),
        tickets / "gone1.md",
    )
    write_ticket(
        Ticket(
            id="self1",
            status="closed",
            title="Self target",
            resolution="superseded",
            close_reason="Superseded",
            superseded_by="self1",
        ),
        tickets / "self1.md",
    )

    issues = resolution_issues(tmp_path)

    assert [issue.code for issue in issues] == [
        "ticket.resolution.invalid",
        "ticket.resolution.invalid",
    ]
    assert any("does not exist" in issue.message for issue in issues)
    assert any("cannot reference itself" in issue.message for issue in issues)


def test_codex_doctor_distinguishes_modified_payload_and_marketplace_drift(tmp_path: Path) -> None:
    install_codex_plugin(tmp_path)
    hooks = tmp_path / "plugins" / "kingdom" / "hooks" / "hooks.json"
    hooks.write_text("{}\n", encoding="utf-8")

    modified = codex_install_issues(tmp_path)

    assert [issue.code for issue in modified] == ["host.codex.plugin_modified"]
    assert "Back up and review" in modified[0].repair

    install_codex_plugin(tmp_path)
    manifest_path = tmp_path / "plugins" / "kingdom" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["description"] = "local description"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    modified_manifest = codex_install_issues(tmp_path)

    assert [issue.code for issue in modified_manifest] == ["host.codex.plugin_modified"]
    assert "Back up and review" in modified_manifest[0].repair

    install_codex_plugin(tmp_path)
    marketplace_path = tmp_path / ".agents" / "plugins" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    marketplace["plugins"][0]["source"]["path"] = "./plugins/wrong"
    marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")

    stale = codex_install_issues(tmp_path)

    assert [issue.code for issue in stale] == ["host.codex.plugin_stale"]
    assert "personal marketplace entry" in stale[0].message


def test_doctor_distinguishes_stale_and_modified_managed_skills(tmp_path: Path) -> None:
    from importlib.resources import files

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    bundle = bundled_skill_files(files("kingdom.skill"))
    stale_bundle = dict(bundle)
    stale_bundle["SKILL.md"] += b"\nold managed version\n"
    target = home / ".codex" / "skills" / "kingdom"
    write_skill_bundle(target, stale_bundle)

    stale = skill_install_issues(home)

    assert [issue.code for issue in stale] == ["host.codex.skill_stale"]
    assert stale[0].repair == "Run `kd update` to refresh the unmodified managed skill."

    (target / "SKILL.md").write_text("local edits\n", encoding="utf-8")
    modified = skill_install_issues(home)

    assert [issue.code for issue in modified] == ["host.codex.skill_modified"]
    assert "Back up and review" in modified[0].repair
