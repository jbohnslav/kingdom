"""Design document CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown

from kingdom.state import branch_root, read_json, resolve_current_run, write_json

from .display import print_error
from .helpers import require_project_root

design_app = typer.Typer(name="design", help="Manage design documents.")


def get_doc_status(path: Path) -> str:
    """Get status of a markdown doc: 'empty', 'draft', or path."""
    if not path.exists():
        return "missing"
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return "empty"
    return "present"


def get_branch_paths(base: Path, feature: str) -> tuple[Path, Path, Path, Path]:
    """Get branch_dir, design.md, breakdown.md, state.json paths.

    Returns: (branch_dir, design_path, breakdown_path, state_path)
    """
    branch_dir = branch_root(base, feature)
    return (
        branch_dir,
        branch_dir / "design.md",
        branch_dir / "breakdown.md",
        branch_dir / "state.json",
    )


def get_design_paths(base: Path, feature: str) -> tuple[Path, Path]:
    """Get design.md and state.json paths, preferring branch structure."""
    _, design_path, _, state_path = get_branch_paths(base, feature)
    return design_path, state_path


@design_app.callback(invoke_without_command=True)
def design_default(ctx: typer.Context) -> None:
    """Print the path to the design document."""
    if ctx.invoked_subcommand is not None:
        return
    base = require_project_root()
    feature = resolve_current_run(base)
    design_path, _ = get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        print_error("No design document found. Run `kd start` to create one.")
        raise typer.Exit(code=1)

    typer.echo(str(design_path.relative_to(base)))


@design_app.command("show", help="Print the design document.")
def design_show() -> None:
    """Print the design.md contents."""
    base = require_project_root()
    feature = resolve_current_run(base)
    design_path, _ = get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        print_error("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    console = Console()
    console.print(Markdown(design_path.read_text(encoding="utf-8")))


@design_app.command("approve", help="Mark the design as approved.")
@design_app.command("accept", hidden=True)
def design_approve() -> None:
    """Set design_approved=true in state.json."""
    base = require_project_root()
    feature = resolve_current_run(base)
    design_path, state_path = get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        print_error("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    state = read_json(state_path) if state_path.exists() else {}
    state["design_approved"] = True
    write_json(state_path, state)
    typer.echo("Design approved")
