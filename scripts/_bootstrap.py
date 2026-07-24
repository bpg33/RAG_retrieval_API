"""Shared bootstrap for scripts: put ``src`` on the path and load ``.env``.

Scripts are read-only discovery/verification tools intended to be run from the
repository root, e.g. ``python scripts/inspect_qdrant.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_env(path: str | os.PathLike[str] | None = None) -> None:
    """Minimal ``.env`` loader (does not override already-set variables)."""
    env_path = Path(path) if path else ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
