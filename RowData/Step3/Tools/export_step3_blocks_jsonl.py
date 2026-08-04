from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
TEXT_PATH = STEP3_DIR / "_extracted_text" / "step3_text.txt"
OUTLINE_PATH = STEP3_DIR / "Data" / "step3_core_outline.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _slugify(text: str) -> str:
    # Keep it safe for IDs/filenames; don’t over-normalize Chinese.
    t = text.strip().lower()
    t = re.sub(r"\s+", "_", t)
    t = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff\-]+", "", t)
    return t[:80] if t else "untitled"


def _extract_lines(lines: list[str], start_line: int, end_line: int) -> str:
    start = max(1, int(start_line))
    end = min(len(lines), int(end_line))
    if end < start:
        return ""
    return "\n".join(lines[start - 1 : end]).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Step3 core outline blocks into JSONL with full text.")
    parser.add_argument(
        "--out",
        default=str(STEP3_DIR / "Data" / "step3_core_blocks.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="If >0, truncate each block text to this many chars",
    )
    args = parser.parse_args()

    if not TEXT_PATH.exists():
        raise SystemExit(f"Missing: {TEXT_PATH}")
    if not OUTLINE_PATH.exists():
        raise SystemExit(f"Missing: {OUTLINE_PATH}")

    lines = TEXT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    outline = _load_json(OUTLINE_PATH)

    singularities = outline.get("singularities")
    if not isinstance(singularities, dict):
        raise SystemExit("Invalid step3_core_outline.json: singularities")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8") as f:
        for major, payload in singularities.items():
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                start_line = item.get("start_line")
                end_line = item.get("end_line")
                if not isinstance(start_line, int) or not isinstance(end_line, int):
                    continue

                num = item.get("num")
                title = str(item.get("title") or "")
                kind = str(item.get("kind") or "")

                text = _extract_lines(lines, start_line, end_line)
                if args.max_chars and args.max_chars > 0:
                    text = text[: args.max_chars]

                record = {
                    "major": major,
                    "num": num,
                    "title": title,
                    "kind": kind,
                    "start_line": start_line,
                    "end_line": end_line,
                    "id": f"{major}-{num or 'NA'}-{_slugify(title)}",
                    "text": text,
                }

                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    print(str(out_path))
    print(f"records={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
