"""Read-only repository and host-integration diagnostics for ``kd doctor``."""

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path

from kingdom.codex_plugin import KINGDOM_PLUGIN_ENTRY, plugin_payloads, read_marketplace
from kingdom.state import parse_context_last_seen
from kingdom.ticket import Ticket, effective_resolution, read_ticket, validate_terminal_evidence


@dataclass(frozen=True)
class DoctorIssue:
    code: str
    message: str
    repair: str
    path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def ticket_files(base: Path) -> list[Path]:
    root = base / ".kd"
    paths = list(root.glob("branches/*/tickets/*.md"))
    paths.extend(root.glob("backlog/tickets/*.md"))
    paths.extend(root.glob("archive/*/tickets/*.md"))
    return sorted(set(paths))


def read_valid_tickets(paths: list[Path]) -> list[tuple[Ticket, Path]]:
    tickets = []
    for path in paths:
        try:
            tickets.append((read_ticket(path), path))
        except (FileNotFoundError, OSError, ValueError):
            continue
    return tickets


def ticket_issues(base: Path) -> list[DoctorIssue]:
    issues = []
    for path in ticket_files(base):
        try:
            read_ticket(path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            issues.append(
                DoctorIssue(
                    code="ticket.invalid",
                    path=str(path.relative_to(base)),
                    message=f"Ticket cannot be read: {exc}.",
                    repair="Restore this file from version control or a known-good `.kd` backup.",
                )
            )
    return issues


def binding_issues(base: Path) -> list[DoctorIssue]:
    issues = []
    root = base / ".kd" / "branches"
    if not root.exists():
        return issues

    for branch in sorted(path for path in root.iterdir() if path.is_dir()):
        tickets = read_valid_tickets(sorted((branch / "tickets").glob("*.md")))
        legacy = sorted(
            ticket.id for ticket, _ in tickets if ticket.status == "in_progress" and ticket.assignee in (None, "hand")
        )
        if len(legacy) > 1:
            choices = ", ".join(legacy)
            issues.append(
                DoctorIssue(
                    code="binding.ambiguous",
                    path=str(branch.relative_to(base)),
                    message=f"Branch {branch.name} has multiple legacy active tickets: {choices}.",
                    repair="Choose the intended ticket, then from that session run `kd tk start <id>`.",
                )
            )

    exact_assignments: dict[str, list[str]] = {}
    for ticket, _ in read_valid_tickets(ticket_files(base)):
        if ticket.status != "in_progress" or ticket.assignee in (None, "hand", "peasant"):
            continue
        exact_assignments.setdefault(ticket.assignee, []).append(ticket.id)
    for assignee, ticket_ids in sorted(exact_assignments.items()):
        if len(ticket_ids) < 2:
            continue
        choices = ", ".join(sorted(ticket_ids))
        issues.append(
            DoctorIssue(
                code="binding.exact_ambiguous",
                path=".kd",
                message=f"Execution context {assignee} is assigned to multiple active tickets: {choices}.",
                repair=(
                    "Decide which ticket the context owns, then from that exact session run "
                    "`kd tk start <id>` and explicitly defer or close stale extras."
                ),
            )
        )
    return issues


def context_ticket_paths(base: Path, context: dict) -> list[Path]:
    ticket_id = context.get("ticket_id")
    location = context.get("location")
    feature = context.get("feature")
    if not isinstance(ticket_id, str) or not ticket_id:
        return []

    if location == "backlog":
        tickets_dir = base / ".kd" / "backlog" / "tickets"
    elif isinstance(location, str) and location.startswith("archive:"):
        tickets_dir = base / ".kd" / "archive" / location.removeprefix("archive:") / "tickets"
    elif isinstance(location, str) and location.startswith("branch:"):
        tickets_dir = base / ".kd" / "branches" / location.removeprefix("branch:") / "tickets"
    elif isinstance(feature, str) and feature:
        tickets_dir = base / ".kd" / "branches" / feature / "tickets"
    else:
        return []
    return [tickets_dir / f"{ticket_id}.md", tickets_dir / f"kin-{ticket_id}.md"]


def ticket_from_context(base: Path, context: dict) -> tuple[Ticket, Path] | None:
    ticket_id = context.get("ticket_id")
    for path in context_ticket_paths(base, context):
        try:
            ticket = read_ticket(path)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if ticket.id == ticket_id:
            return ticket, path
    return None


def global_ticket_matches(base: Path, ticket_id: str) -> list[tuple[Ticket, Path]]:
    return [(ticket, path) for ticket, path in read_valid_tickets(ticket_files(base)) if ticket.id == ticket_id]


def context_has_unreadable_ticket(base: Path, context: dict) -> bool:
    for path in context_ticket_paths(base, context):
        if not path.exists():
            continue
        try:
            read_ticket(path)
        except (FileNotFoundError, OSError, ValueError):
            return True
    return False


def context_record_is_valid(context: dict) -> bool:
    return (
        isinstance(context.get("context_id"), str)
        and bool(context["context_id"])
        and isinstance(context.get("host"), str)
        and bool(context["host"])
        and parse_context_last_seen(context.get("last_seen")) is not None
    )


def move_aside_repair(base: Path, path: Path) -> str:
    relative = str(path.relative_to(base))
    source = shlex.quote(relative)
    destination = shlex.quote(f"{relative}.bak")
    return f"After confirming the session is inactive, run `mv -n {source} {destination}`."


def binding_mismatch_repair(base: Path, path: Path, ticket: Ticket, context_id: str) -> str:
    if ticket.status == "in_progress" and ticket.assignee in (None, "hand", context_id):
        return f"After confirming this session owns the ticket, run `kd tk start {ticket.id}`."
    return move_aside_repair(base, path)


def execution_context_issues(base: Path) -> list[DoctorIssue]:
    issues = []
    contexts_root = base / ".kd" / "runtime" / "contexts"
    if not contexts_root.exists():
        return issues

    for path in sorted(contexts_root.glob("*.json")):
        relative = str(path.relative_to(base))
        try:
            context = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(
                DoctorIssue(
                    code="context.invalid",
                    path=relative,
                    message=f"Context record is unreadable: {exc}.",
                    repair=move_aside_repair(base, path),
                )
            )
            continue
        if not isinstance(context, dict) or not context_record_is_valid(context):
            issues.append(
                DoctorIssue(
                    code="context.invalid",
                    path=relative,
                    message="Context record is partial or missing required identity/timestamp fields.",
                    repair=move_aside_repair(base, path),
                )
            )
            continue
        if context.get("active") is False:
            continue

        ticket_id = context.get("ticket_id")
        if not isinstance(ticket_id, str) or not ticket_id:
            continue
        resolved = ticket_from_context(base, context)
        if resolved is None:
            matches = global_ticket_matches(base, ticket_id)
            if len(matches) == 1:
                ticket, actual_path = matches[0]
                issues.append(
                    DoctorIssue(
                        code="binding.location_mismatch",
                        path=relative,
                        message=(
                            f"Context {context['context_id']} records a stale location for {ticket.id}; "
                            f"the ticket is at {actual_path.relative_to(base)}."
                        ),
                        repair=binding_mismatch_repair(base, path, ticket, context["context_id"]),
                    )
                )
                continue
            if context_has_unreadable_ticket(base, context):
                continue
            detail = "multiple ticket files with that ID" if matches else "no matching ticket"
            issues.append(
                DoctorIssue(
                    code="context.orphan",
                    path=relative,
                    message=f"Context {context['context_id']} points to {ticket_id}, but found {detail}.",
                    repair=move_aside_repair(base, path),
                )
            )
            continue

        ticket, _ = resolved
        parent = context.get("parent_agent_id")
        shared_with_parent = context.get("role") == "subagent" and parent == ticket.assignee
        if ticket.status == "in_progress" and (ticket.assignee == context["context_id"] or shared_with_parent):
            continue
        issues.append(
            DoctorIssue(
                code="binding.mismatch",
                path=relative,
                message=(
                    f"Context {context['context_id']} claims {ticket.id}, but the ticket is "
                    f"{ticket.status} and assigned to {ticket.assignee or 'nobody'}."
                ),
                repair=binding_mismatch_repair(base, path, ticket, context["context_id"]),
            )
        )
    return issues


def legacy_context_issues(base: Path) -> list[DoctorIssue]:
    issues = []
    contexts_root = base / ".kd" / "runtime" / "terminal-context"
    if not contexts_root.exists():
        return issues

    for path in sorted(contexts_root.glob("*.json")):
        relative = str(path.relative_to(base))
        try:
            context = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(
                DoctorIssue(
                    code="context.invalid",
                    path=relative,
                    message=f"Legacy terminal context is unreadable: {exc}.",
                    repair=move_aside_repair(base, path),
                )
            )
            continue
        if not isinstance(context, dict) or not isinstance(context.get("ticket_id"), str):
            issues.append(
                DoctorIssue(
                    code="context.invalid",
                    path=relative,
                    message="Legacy terminal context is missing its ticket identity.",
                    repair=move_aside_repair(base, path),
                )
            )
            continue

        ticket_id = context["ticket_id"]
        resolved = ticket_from_context(base, context)
        if resolved is None:
            matches = global_ticket_matches(base, ticket_id)
            if len(matches) == 1 and matches[0][0].status == "in_progress":
                ticket, actual_path = matches[0]
                issues.append(
                    DoctorIssue(
                        code="binding.location_mismatch",
                        path=relative,
                        message=(
                            f"Legacy terminal context records a stale location for {ticket.id}; "
                            f"the ticket is at {actual_path.relative_to(base)}."
                        ),
                        repair=f"From the owning terminal run `kd tk start {ticket.id}`.",
                    )
                )
                continue
            if context_has_unreadable_ticket(base, context):
                continue
            issues.append(
                DoctorIssue(
                    code="context.orphan",
                    path=relative,
                    message=f"Legacy terminal context points to missing or ambiguous ticket {ticket_id}.",
                    repair=move_aside_repair(base, path),
                )
            )
            continue
        ticket, _ = resolved
        if ticket.status != "in_progress":
            issues.append(
                DoctorIssue(
                    code="binding.mismatch",
                    path=relative,
                    message=f"Legacy terminal context claims {ticket.id}, but the ticket is {ticket.status}.",
                    repair=move_aside_repair(base, path),
                )
            )
    return issues


def context_issues(base: Path) -> list[DoctorIssue]:
    return [*execution_context_issues(base), *legacy_context_issues(base)]


def resolution_issues(base: Path) -> list[DoctorIssue]:
    issues = []
    tickets = read_valid_tickets(ticket_files(base))
    known_ids = {ticket.id for ticket, _ in tickets}
    for ticket, path in tickets:
        if ticket.status != "closed":
            continue
        errors = validate_terminal_evidence(ticket)
        resolution = effective_resolution(ticket)
        reference = ticket.duplicate_of if resolution == "duplicate" else ticket.superseded_by
        if reference == ticket.id:
            errors.append(f"{resolution} target cannot reference itself")
        elif reference and reference not in known_ids:
            errors.append(f"{resolution} target {reference} does not exist")
        if not errors:
            continue
        issues.append(
            DoctorIssue(
                code="ticket.resolution.invalid",
                path=str(path.relative_to(base)),
                message=f"Ticket {ticket.id} has invalid closure metadata: {'; '.join(errors)}.",
                repair=(
                    f"Run `kd tk reopen {ticket.id}`, then close it again with the intended "
                    "`--resolution` and required reason/reference options."
                ),
            )
        )
    return issues


def claude_settings_shape_is_valid(settings: object) -> bool:
    if not isinstance(settings, dict):
        return False
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    for event_hooks in hooks.values():
        if not isinstance(event_hooks, list):
            return False
        for matcher in event_hooks:
            if not isinstance(matcher, dict):
                return False
            commands = matcher.get("hooks", [])
            if not isinstance(commands, list) or any(not isinstance(command, dict) for command in commands):
                return False
    return True


def claude_install_issues(base: Path) -> list[DoctorIssue]:
    from kingdom.cli.plugin import (
        SUPPORTED_HOOK_EVENTS,
        has_full_hook_installation,
        has_hook_for_event,
        has_legacy_hook_installation,
        read_settings,
    )

    settings_path = base / ".claude" / "settings.json"
    try:
        settings = read_settings(settings_path)
    except (OSError, ValueError) as exc:
        return [
            DoctorIssue(
                code="host.claude.settings_invalid",
                path=str(settings_path.relative_to(base)),
                message=str(exc),
                repair="Repair the JSON manually, then run `kd plugin enable`.",
            )
        ]
    if not claude_settings_shape_is_valid(settings):
        return [
            DoctorIssue(
                code="host.claude.settings_invalid",
                path=str(settings_path.relative_to(base)),
                message="Claude settings have an invalid hooks structure.",
                repair="Back up and repair the JSON structure, then run `kd plugin enable`.",
            )
        ]

    if has_legacy_hook_installation(settings):
        return [
            DoctorIssue(
                code="host.claude.hooks_legacy",
                path=str(settings_path.relative_to(base)),
                message="Claude uses Kingdom's retired hook script command.",
                repair="Run `kd plugin enable` to replace legacy hooks and add current lifecycle coverage.",
            )
        ]
    installed_events = [event for event in SUPPORTED_HOOK_EVENTS if has_hook_for_event(settings, event)]
    if not installed_events or has_full_hook_installation(settings):
        return []
    missing = ", ".join(event for event in SUPPORTED_HOOK_EVENTS if event not in installed_events)
    return [
        DoctorIssue(
            code="host.claude.hooks_legacy",
            path=str(settings_path.relative_to(base)),
            message=f"Claude has legacy Kingdom lifecycle coverage; missing: {missing}.",
            repair="Run `kd plugin enable` to add the missing hooks without replacing other settings.",
        )
    ]


def managed_codex_manifest(path: Path, expected: bytes) -> bool:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        expected_manifest = json.loads(expected)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(manifest, dict) or not isinstance(expected_manifest, dict):
        return False
    version = manifest.get("version")
    if not isinstance(version, str) or "+codex." not in version:
        return False
    comparable = dict(manifest)
    comparable["version"] = expected_manifest.get("version")
    return comparable == expected_manifest


def codex_install_issues(home: Path) -> list[DoctorIssue]:
    plugin_root = home / "plugins" / "kingdom"
    marketplace_path = home / ".agents" / "plugins" / "marketplace.json"
    try:
        marketplace = read_marketplace(marketplace_path)
    except (OSError, ValueError) as exc:
        if not plugin_root.exists():
            return []
        return [
            DoctorIssue(
                code="host.codex.plugin_modified",
                path=str(marketplace_path),
                message=f"Codex's marketplace cannot be inspected safely: {exc}.",
                repair="Back up and review the marketplace before running `kd plugin install codex`.",
            )
        ]

    kingdom_entries = [
        entry for entry in marketplace["plugins"] if isinstance(entry, dict) and entry.get("name") == "kingdom"
    ]
    if not plugin_root.exists() and not kingdom_entries:
        return []

    expected_payloads = plugin_payloads()
    drift = []
    for relative, expected in expected_payloads.items():
        path = plugin_root / relative
        try:
            current = path.read_bytes()
        except OSError:
            drift.append(relative)
            continue
        if current != expected:
            drift.append(relative)
    if kingdom_entries != [KINGDOM_PLUGIN_ENTRY]:
        drift.append("personal marketplace entry")
    if not drift:
        return []

    payload_drift = [item for item in drift if item != "personal marketplace entry"]
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    expected_manifest = expected_payloads[".codex-plugin/plugin.json"]
    try:
        manifest_is_current = manifest_path.read_bytes() == expected_manifest
    except OSError:
        manifest_is_current = False
    locally_modified = bool(payload_drift) and plugin_root.exists() and manifest_is_current
    if (
        payload_drift
        and plugin_root.exists()
        and not locally_modified
        and not managed_codex_manifest(manifest_path, expected_manifest)
    ):
        locally_modified = True

    if locally_modified:
        return [
            DoctorIssue(
                code="host.codex.plugin_modified",
                path=str(plugin_root),
                message=f"Codex Kingdom plugin has local or unknown changes: {', '.join(sorted(set(drift)))}.",
                repair=(
                    "Back up and review the listed plugin files before running `kd plugin install codex`; "
                    "the installer replaces differing managed files."
                ),
            )
        ]
    return [
        DoctorIssue(
            code="host.codex.plugin_stale",
            path=str(plugin_root),
            message=f"Codex Kingdom plugin is incomplete or stale: {', '.join(sorted(set(drift)))}.",
            repair=(
                "Back up the existing plugin directory, then run `kd plugin install codex` to refresh "
                "Kingdom-managed plugin files and activation."
            ),
        )
    ]


def skill_install_issues(home: Path) -> list[DoctorIssue]:
    from kingdom.cli.helpers import (
        SKILL_MANIFEST,
        bundled_skill_files,
        read_skill_manifest,
        skill_targets,
        target_matches_bundle,
        target_matches_hashes,
    )

    bundle = bundled_skill_files(files("kingdom.skill"))
    issues = []
    for target in skill_targets(home):
        if not target.enabled or target.path.is_symlink() or not target.path.exists():
            continue
        manifest_path = target.path / SKILL_MANIFEST
        hashes = read_skill_manifest(manifest_path)
        if manifest_path.exists() and hashes is None:
            modified = True
        elif hashes is None:
            # Without a manifest, the directory might be user-managed. Avoid
            # claiming ownership or recommending a potentially destructive refresh.
            continue
        else:
            modified = not target_matches_hashes(target.path, hashes)
        if modified:
            issues.append(
                DoctorIssue(
                    code=f"host.{target.host}.skill_modified",
                    path=str(target.path),
                    message=f"The {target.host} Kingdom skill has local or unknown changes.",
                    repair="Back up and review the skill files before running `kd update`.",
                )
            )
            continue
        if target_matches_bundle(target.path, bundle):
            continue
        issues.append(
            DoctorIssue(
                code=f"host.{target.host}.skill_stale",
                path=str(target.path),
                message=f"The {target.host} Kingdom skill is an older unmodified managed version.",
                repair="Run `kd update` to refresh the unmodified managed skill.",
            )
        )
    return issues


def host_install_issues(base: Path, home: Path) -> list[DoctorIssue]:
    return [*claude_install_issues(base), *codex_install_issues(home), *skill_install_issues(home)]
