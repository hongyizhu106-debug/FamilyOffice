from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Step3.Constructor.relations_catalog import write_relations_structured


def main() -> int:
    out_path = write_relations_structured()
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
