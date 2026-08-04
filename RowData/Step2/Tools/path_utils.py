from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """Best-effort repo root finder.

    Walk upward from `start` until we find the workspace root which contains
    README.md and both Step1/ and Step2/.

    Falls back to `start` if not found.
    """

    start = start.resolve()
    for parent in [start, *start.parents]:
        if (parent / "README.md").exists() and (parent / "Step1").exists() and (parent / "Step2").exists():
            return parent
    return start
