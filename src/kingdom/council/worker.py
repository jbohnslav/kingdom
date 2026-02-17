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

from rich.console import Console

from kingdom.council.council import Council
from kingdom.state import logs_root
from kingdom.thread import add_message


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Council async worker")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--to", default=None, dest="to_member")
    parser.add_argument("--writable", action="store_true", default=False)
    args = parser.parse_args(argv)

    logs_dir = logs_root(args.base, args.feature)
    logs_dir.mkdir(parents=True, exist_ok=True)

    c = Council.create(logs_dir=logs_dir, base=args.base)
    if args.writable:
        for member in c.members:
            member.writable = True
    c.timeout = args.timeout
    c.load_sessions(args.base, args.feature)

    if args.to_member:
        from kingdom.thread import thread_dir

        member = c.get_member(args.to_member)
        if member is None:
            Console(stderr=True).print(f"[red]Unknown member: {args.to_member}[/red]")
            sys.exit(1)

        tdir = thread_dir(args.base, args.feature, args.thread_id)
        tdir.mkdir(parents=True, exist_ok=True)
        stream_path = tdir / f".stream-{member.name}.jsonl"

        response = member.query(args.prompt, args.timeout, stream_path=stream_path)
        add_message(
            args.base,
            args.feature,
            args.thread_id,
            from_=args.to_member,
            to="king",
            body=response.thread_body(),
        )

        if stream_path.exists():
            stream_path.unlink()
    else:
        c.query_to_thread(args.prompt, args.base, args.feature, args.thread_id)

    c.save_sessions(args.base, args.feature)


if __name__ == "__main__":
    main()
