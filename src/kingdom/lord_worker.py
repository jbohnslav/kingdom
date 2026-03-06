"""Worker entry point for the lord agent loop.

Invoked as ``python -m kingdom.lord_worker`` by ``kd lord start``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run the lord harness loop. Returns 0 on success, 1 on failure."""
    parser = argparse.ArgumentParser(description="Run lord agent loop on an epic.")
    parser.add_argument("epic_id", help="Epic ticket ID")
    parser.add_argument("--agent", required=True, help="Agent backend name")
    parser.add_argument("--session", required=True, help="Session name")
    parser.add_argument("--base", required=True, help="Project root")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    from kingdom.lord_harness import run_lord_loop
    from kingdom.state import resolve_current_run

    base = Path(args.base).resolve()
    feature = resolve_current_run(base)

    status = run_lord_loop(
        base=base,
        branch=feature,
        agent_name=args.agent,
        epic_id=args.epic_id,
        session_name=args.session,
    )

    return 0 if status in ("done", "blocked", "stopped") else 1


if __name__ == "__main__":
    sys.exit(main())
