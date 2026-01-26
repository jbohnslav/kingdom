"""Plan parsing helpers."""

from __future__ import annotations

import re
from typing import Any


def parse_plan_tickets(plan_text: str) -> list[dict[str, Any]]:
    lines = plan_text.splitlines()
    in_tickets = False
    tickets: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    collecting_acceptance = False

    header_re = re.compile(r"^- \[[ xX]\] (?P<id>[^:]+): (?P<title>.+)$")

    for line in lines:
        if line.startswith("## "):
            in_tickets = line.strip() == "## Tickets"
            collecting_acceptance = False
            current = None
            continue

        if not in_tickets:
            continue

        match = header_re.match(line)
        if match:
            current = {
                "plan_id": match.group("id").strip(),
                "title": match.group("title").strip(),
                "priority": 2,
                "depends_on": [],
                "description": "",
                "acceptance": [],
            }
            tickets.append(current)
            collecting_acceptance = False
            continue

        if current is None:
            continue

        if line.startswith("  - "):
            collecting_acceptance = False
            key, _, value = line[4:].partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "priority":
                if value.isdigit():
                    current["priority"] = int(value)
            elif key == "depends on":
                if value.lower() != "none":
                    deps = [item.strip() for item in value.split(",") if item.strip()]
                    current["depends_on"] = deps
            elif key == "description":
                current["description"] = value
            elif key == "acceptance":
                collecting_acceptance = True
            continue

        if collecting_acceptance and line.strip().startswith("-"):
            item = line.strip()
            item = item.removeprefix("- [ ]").removeprefix("-").strip()
            current["acceptance"].append(item)

    return tickets
