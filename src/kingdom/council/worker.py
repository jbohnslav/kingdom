"""Background worker for async council queries.

Invoked as a subprocess by ``kd council ask`` (default async dispatch)::

    python -m kingdom.council.worker \\
        --base /path/to/project \\
        --feature branch-name \\
        --thread-id council-abcd \\
        --prompt "the question" \\
        --timeout 120 \\
        [--to member-name]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kingdom.council.council import Council
from kingdom.state import logs_root
from kingdom.thread import add_message


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Council async worker")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--to", default=None, dest="to_member")
    args = parser.parse_args(argv)

    logs_dir = logs_root(args.base, args.feature)
    logs_dir.mkdir(parents=True, exist_ok=True)

    c = Council.create(logs_dir=logs_dir, base=args.base)
    c.timeout = args.timeout
    c.load_sessions(args.base, args.feature)

    if args.to_member:
        member = c.get_member(args.to_member)
        if member is None:
            print(f"Unknown member: {args.to_member}", file=sys.stderr)
            sys.exit(1)
        response = member.query(args.prompt, args.timeout)
        body = response.text if response.text else f"*Error: {response.error}*"
        add_message(args.base, args.feature, args.thread_id, from_=args.to_member, to="king", body=body)
    else:
        c.query_to_thread(args.prompt, args.base, args.feature, args.thread_id)

    c.save_sessions(args.base, args.feature)


if __name__ == "__main__":
    main()
