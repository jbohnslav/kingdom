"""TUI chat interface for council conversations.

Requires the ``chat`` dependency group::

    uv sync --group chat
"""

from __future__ import annotations


def require_textual() -> None:
    """Raise a clear error if textual is not installed."""
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "The 'textual' package is required for kd chat.\n" "Install it with: uv sync --group chat"
        ) from exc
