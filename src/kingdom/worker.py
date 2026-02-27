"""Worker entry point for the peasant agent loop.

Invoked as ``python -m kingdom.worker`` by :func:`kingdom.cli.launch_work_background`
and :func:`kingdom.cli.launch_work_tmux`.  All arguments are required — context
resolution happens in the CLI layer before launch.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run the agent harness loop. Returns 0 on success, 1 on failure."""
    parser = argparse.ArgumentParser(description="Run autonomous agent loop on a ticket.")
    parser.add_argument("ticket_id", help="Ticket ID")
    parser.add_argument("--agent", required=True, help="Agent backend name")
    parser.add_argument("--worktree", required=True, help="Worktree path")
    parser.add_argument("--thread", required=True, help="Thread ID")
    parser.add_argument("--session", required=True, help="Session name")
    parser.add_argument("--base", required=True, help="Project root")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    from kingdom.harness import run_agent_loop
    from kingdom.state import resolve_current_run

    base = Path(args.base).resolve()
    feature = resolve_current_run(base)
    worktree_path = Path(args.worktree).resolve()

    status = run_agent_loop(
        base=base,
        branch=feature,
        agent_name=args.agent,
        ticket_id=args.ticket_id,
        worktree=worktree_path,
        thread_id=args.thread,
        session_name=args.session,
    )

    return 0 if status == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
