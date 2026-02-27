"""Council package for multi-agent orchestration."""

from __future__ import annotations

from pathlib import Path

from .base import AgentResponse, CouncilMember
from .bundle import create_run_bundle, generate_run_id
from .council import Council


def create_council(
    base: Path,
    feature: str,
    *,
    writable: bool = False,
    timeout: int | None = None,
) -> Council:
    """Create a Council with logs dir, sessions loaded, and optional overrides.

    This is the standard way to get a ready-to-use Council in CLI commands
    and the async worker.
    """
    from kingdom.state import logs_root

    logs_dir = logs_root(base, feature)
    logs_dir.mkdir(parents=True, exist_ok=True)

    c = Council.create(logs_dir=logs_dir, base=base)
    if writable:
        for m in c.members:
            m.writable = True
    if timeout is not None:
        c.timeout = timeout
    c.load_sessions(base, feature)
    return c


__all__ = [
    "AgentResponse",
    "Council",
    "CouncilMember",
    "create_council",
    "create_run_bundle",
    "generate_run_id",
]
