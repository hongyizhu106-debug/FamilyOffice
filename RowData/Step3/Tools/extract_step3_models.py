from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
INDEX_PATH = STEP3_DIR / "Data" / "step3_index.json"
TEXT_PATH = STEP3_DIR / "_extracted_text" / "step3_text.txt"


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    if not INDEX_PATH.exists() or not TEXT_PATH.exists():
        raise SystemExit("Missing step3_index.json or step3_text.txt")

    idx = _load_json(INDEX_PATH)
    blocks = idx.get("blocks")
    if not isinstance(blocks, list):
        raise SystemExit("Invalid index format: blocks")

    keywords = [
        "模型",
        "维度",
        "阈值",
        "指标",
        "传导路径",
        "共振风险",
        "归因分析",
        "防御策略",
        "飞轮",
    ]

    picked: list[dict[str, Any]] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        title = str(b.get("title") or "")
        kind = str(b.get("kind") or "")
        if kind not in {"num", "cn_main", "layer"}:
            continue

        if any(k in title for k in keywords):
            picked.append(
                {
                    "start_line": b.get("start_line"),
                    "end_line": b.get("end_line"),
                    "kind": kind,
                    "num": b.get("num"),
                    "title": title,
                    "preview": b.get("preview"),
                }
            )

    out = {
        "source_index": str(INDEX_PATH),
        "source_text": str(TEXT_PATH),
        "count": len(picked),
        "items": picked,
        "keywords": keywords,
    }

    out_path = STEP3_DIR / "Data" / "step3_models_and_rules_index.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
