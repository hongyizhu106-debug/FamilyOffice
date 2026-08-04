from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """Best-effort repo root finder.

    Walks upward from `start` until it finds a directory containing `README.md`
    and `Step1/` (current project layout). Falls back to `start` if not found.
    """

    start = start.resolve()
    for parent in [start, *start.parents]:
        if (parent / "README.md").exists() and (parent / "Step1").exists():
            return parent
    return start
