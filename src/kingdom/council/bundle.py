"""Council run bundle management."""

import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kingdom.state import write_json

from .base import AgentResponse


def generate_run_id() -> str:
    """Generate run ID in format: run-<4hex>."""
    return f"run-{secrets.token_hex(2)}"


def create_run_bundle(
    council_logs_dir: Path,
    prompt: str,
    responses: dict[str, AgentResponse],
) -> dict[str, Any]:
    """Create a run bundle directory with response files."""
    run_id = generate_run_id()
    run_dir = council_logs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    errors: dict[str, str] = {}

    # Write per-member markdown files
    for name, response in responses.items():
        md_path = run_dir / f"{name}.md"
        content = _format_response_markdown(response)
        md_path.write_text(content, encoding="utf-8")
        paths[name] = md_path
        if response.error:
            errors[name] = response.error

    # Write metadata.json
    metadata = _build_metadata(prompt, responses)
    write_json(run_dir / "metadata.json", metadata)

    # Write errors.json if any failures
    if errors:
        write_json(run_dir / "errors.json", errors)

    return {"run_id": run_id, "run_dir": run_dir, "paths": paths}


def _format_response_markdown(response: AgentResponse) -> str:
    """Format an AgentResponse as markdown."""
    lines = [f"# {response.name}", ""]
    if response.error:
        lines.append(f"> **Error:** {response.error}\n")
    lines.append(response.text if response.text else "*No response*")
    lines.extend(["", "---", f"*Elapsed: {response.elapsed:.1f}s*"])
    return "\n".join(lines)


def _build_metadata(prompt: str, responses: dict[str, AgentResponse]) -> dict:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "prompt": prompt,
        "members": {
            name: {"elapsed": r.elapsed, "error": r.error, "has_response": bool(r.text)}
            for name, r in responses.items()
        },
    }
