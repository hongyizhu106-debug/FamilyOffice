from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
INDEX_PATH = STEP3_DIR / "Data" / "step3_index.json"


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    idx = _load_json(INDEX_PATH)
    blocks = idx.get("blocks")
    if not isinstance(blocks, list):
        raise SystemExit("Invalid step3_index.json: blocks")

    # Keys we want to track for each singularity section.
    focus_terms = [
        "模型",
        "维度",
        "分类",
        "阈值",
        "监测",
        "防御",
        "策略",
        "传导",
        "共振",
        "归因",
        "案例",
        "飞轮",
        "韧性",
    ]

    # Map 1..7 to singularity names as used in Step3 headings.
    singularities = {
        1: "人物",
        2: "认知/文化",
        3: "权力/决策",
        4: "时间",
        5: "财务",
        6: "技术",
        7: "事件",
    }

    def pick_block(b: dict[str, Any]) -> dict[str, Any]:
        return {
            "num": b.get("num"),
            "title": b.get("title"),
            "kind": b.get("kind"),
            "start_line": b.get("start_line"),
            "end_line": b.get("end_line"),
            "preview": b.get("preview"),
        }

    out: dict[str, Any] = {
        "source": str(INDEX_PATH),
        "focus_terms": focus_terms,
        "singularities": {},
    }

    # Match e.g. 3.6.2 etc
    num_re = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?$")

    for major, sname in singularities.items():
        items: list[dict[str, Any]] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            num = b.get("num")
            if not isinstance(num, str):
                continue
            m = num_re.match(num)
            if not m:
                continue
            if int(m.group(1)) != major:
                continue

            title = str(b.get("title") or "")
            if any(t in title for t in focus_terms):
                items.append(pick_block(b))

        out["singularities"][str(major)] = {
            "name": sname,
            "count": len(items),
            "items": items,
        }

    out_path = STEP3_DIR / "Data" / "step3_core_outline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
