"""
Add a git submodule under `third-party/`.

Usage:
  uv run scripts/add_submodule.py <name> <url> [--branch main]

Example:
  uv run scripts/add_submodule.py ticket https://github.com/wedow/ticket --branch main
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add a git submodule under third-party/.")
    parser.add_argument("name", help="Folder name under third-party/ (e.g. 'ticket').")
    parser.add_argument("url", help="Git URL (https or ssh).")
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch to track for the initial add (passed to `git submodule add -b`).",
    )
    return parser.parse_args(argv)


def validate_name(name: str) -> str:
    if "/" in name or "\\" in name:
        raise ValueError("name must be a single path segment (no slashes)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("name must match: [A-Za-z0-9][A-Za-z0-9._-]*")
    return name


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    name = validate_name(args.name)

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    third_party_dir = repo_root / "third-party"
    third_party_dir.mkdir(parents=True, exist_ok=True)

    target_dir = third_party_dir / name
    if target_dir.exists():
        raise FileExistsError(f"target already exists: {target_dir}")

    target_dir_relative = target_dir.relative_to(repo_root)

    command = ["git", "submodule", "add"]
    if args.branch:
        command.extend(["-b", args.branch])
    command.extend([args.url, str(target_dir_relative)])
    run(command)

    print("Submodule added.")
    print("Next:")
    print(f"  - Commit `.gitmodules` and `{target_dir.relative_to(repo_root)}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
