"""Ensure tests import kingdom from this worktree, not from an external editable install."""

import sys
from pathlib import Path

# Prepend this worktree's src/ so tests always use local code,
# even when pytest is invoked by a Python from a different venv.
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
