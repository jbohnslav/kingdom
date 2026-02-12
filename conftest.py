"""Ensure the worktree's own source is importable, even when pytest
is launched by a Python whose site-packages point elsewhere (e.g. the
parent repo's editable install)."""

import importlib
import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
    # Force re-import so the worktree's kingdom is loaded
    for mod_name in [m for m in sys.modules if m == "kingdom" or m.startswith("kingdom.")]:
        del sys.modules[mod_name]
    importlib.invalidate_caches()
