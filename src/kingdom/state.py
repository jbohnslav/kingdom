"""State layout helpers for Kingdom runs.

Example:
    from pathlib import Path
    from kingdom.state import ensure_run_layout, set_current_run, resolve_current_run

    root = Path(".")
    ensure_run_layout(root, "example")
    set_current_run(root, "example")
    resolve_current_run(root)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def state_root(base: Path) -> Path:
    return base / ".kd"


def runs_root(base: Path) -> Path:
    return state_root(base) / "runs"


def run_root(base: Path, feature: str) -> Path:
    return runs_root(base) / feature


def logs_root(base: Path, feature: str) -> Path:
    return run_root(base, feature) / "logs"


def sessions_root(base: Path, feature: str) -> Path:
    return run_root(base, feature) / "sessions"


def hand_session_path(base: Path, feature: str) -> Path:
    """Path to the Hand's session file."""
    return sessions_root(base, feature) / "hand.session"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return {}
    return json.loads(content)


def write_json(path: Path, data: dict[str, Any]) -> None:
    serialized = json.dumps(data, indent=2, sort_keys=True)
    path.write_text(f"{serialized}\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    serialized = json.dumps(record, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{serialized}\n")


def ensure_run_layout(base: Path, feature: str) -> dict[str, Path]:
    ensure_dir(state_root(base))
    ensure_dir(runs_root(base))

    run_dir = run_root(base, feature)
    ensure_dir(run_dir)
    ensure_dir(logs_root(base, feature))
    ensure_dir(sessions_root(base, feature))

    config_path = state_root(base) / "config.json"
    if not config_path.exists():
        write_json(config_path, {})

    state_path = run_dir / "state.json"
    if not state_path.exists():
        write_json(state_path, {})

    plan_path = run_dir / "plan.md"
    if not plan_path.exists():
        plan_path.write_text("", encoding="utf-8")

    return {
        "state_root": state_root(base),
        "run_root": run_dir,
        "logs_root": logs_root(base, feature),
        "sessions_root": sessions_root(base, feature),
        "config_json": config_path,
        "state_json": state_path,
        "plan_md": plan_path,
    }


def set_current_run(base: Path, feature: str) -> None:
    ensure_dir(state_root(base))
    current_path = state_root(base) / "current"
    current_path.write_text(f"{feature}\n", encoding="utf-8")


def resolve_current_run(base: Path) -> str:
    current_path = state_root(base) / "current"
    if not current_path.exists():
        raise RuntimeError("No active run. Use `kd start <feature>` first.")

    feature = current_path.read_text(encoding="utf-8").strip()
    if not feature:
        raise RuntimeError("Current run is empty. Use `kd start <feature>` again.")

    run_dir = run_root(base, feature)
    if not run_dir.exists():
        raise RuntimeError(f"Current run '{feature}' not found at {run_dir}.")

    return feature
