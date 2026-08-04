from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
TEXT_PATH = STEP3_DIR / "_extracted_text" / "step3_text.txt"


def main() -> int:
    if not TEXT_PATH.exists():
        raise SystemExit(f"Missing {TEXT_PATH}")

    text = TEXT_PATH.read_text(encoding="utf-8", errors="ignore")

    # Role tags like R-Init, D-Det, A-Amp, A-Lock, C-Con, T-Term.
    role_re = re.compile(r"\b([A-Z])\-([A-Za-z]{2,12})\b")
    roles = role_re.findall(text)
    role_counts = Counter([f"{a}-{b}" for a, b in roles])

    # Other shorthand tokens frequently used in formulas/tables.
    tokens_re = re.compile(r"\bK(?:\d+)?\b|K[₀-₉]+|\bfx\b|\bf\(x\)\b", re.IGNORECASE)
    token_counts = Counter(tokens_re.findall(text))

    out = {
        "source_text": str(TEXT_PATH),
        "roles": {
            "unique": sorted(role_counts.keys()),
            "counts": dict(role_counts.most_common(50)),
        },
        "tokens": {
            "unique": sorted(token_counts.keys()),
            "counts": dict(token_counts.most_common(50)),
        },
    }

    out_path = STEP3_DIR / "Data" / "step3_lexicon.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
