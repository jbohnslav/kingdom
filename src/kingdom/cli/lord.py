"""Lord CLI commands — orchestrates peasant workers on an epic."""

from __future__ import annotations

from typing import Annotated

import typer

lord_app = typer.Typer(name="lord", help="Lord mode — orchestrate peasants on an epic.")


@lord_app.command()
def start(
    epic_id: Annotated[str, typer.Argument(help="Epic ticket ID to orchestrate.")],
) -> None:
    """Start the lord agent on an epic (runs on feature branch, delegates to peasant worktrees)."""
    typer.echo(f"kd lord start: not yet implemented (epic: {epic_id})")
    raise typer.Exit(code=0)


@lord_app.command()
def stop() -> None:
    """Signal the lord agent to stop gracefully."""
    typer.echo("kd lord stop: not yet implemented")
    raise typer.Exit(code=0)
