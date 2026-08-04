from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STEP3_DIR = REPO_ROOT / "Step3"
TEXT_PATH = STEP3_DIR / "_extracted_text" / "step3_text.txt"


@dataclass(frozen=True)
class Heading:
    line: int
    kind: str  # num|layer|cn_main
    num: str | None
    title: str


_NUM_HEADING_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)*)\s*[\.、]?\s*(?P<title>[^\s].{0,120})\s*$")
_LAYER_RE = re.compile(r"^\s*第[一二三四五六七八九十]+层[:：].+$")
_CN_MAIN_RE = re.compile(r"^\s*[一二三四五六七八九十]+、\s*.+$")


def is_noise_numeric_heading(title: str) -> bool:
    # Filter table-like arrows: "2 → 1" etc.
    t = title.strip()
    if "→" in t and len(t) <= 8:
        return True
    return False


def extract_headings(lines: list[str]) -> list[Heading]:
    headings: list[Heading] = []
    for idx, raw in enumerate(lines, start=1):
        s = raw.strip()
        if not s:
            continue

        m = _NUM_HEADING_RE.match(s)
        if m:
            num = m.group("num")
            title = m.group("title").strip()
            if is_noise_numeric_heading(title):
                continue
            headings.append(Heading(line=idx, kind="num", num=num, title=title))
            continue

        if _LAYER_RE.match(s):
            headings.append(Heading(line=idx, kind="layer", num=None, title=s))
            continue

        if _CN_MAIN_RE.match(s):
            headings.append(Heading(line=idx, kind="cn_main", num=None, title=s))

    return headings


_KEYWORDS = [
    "模型",
    "预警阈",
    "关键监测指标",
    "监测预警体系",
    "主动防御策略",
    "归因分析案例",
    "归因分析流程",
    "核心传导路径",
    "共振风险",
    "飞轮",
]


def extract_keyword_hits(lines: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for i, raw in enumerate(lines, start=1):
        s = raw.strip()
        if not s:
            continue
        for kw in _KEYWORDS:
            if kw in s:
                hits.append({"line": i, "keyword": kw, "text": s[:200]})
                break
    return hits


def build_blocks(lines: list[str], headings: list[Heading]) -> list[dict[str, Any]]:
    # Create blocks between headings for navigation.
    hs = sorted(headings, key=lambda h: h.line)
    out: list[dict[str, Any]] = []
    for i, h in enumerate(hs):
        start = h.line
        end = (hs[i + 1].line - 1) if i + 1 < len(hs) else len(lines)
        # store a short preview only; full text remains in step3_text.txt
        preview = "\n".join(lines[start - 1 : min(end, start + 40) - 1]).strip()
        out.append(
            {
                "start_line": start,
                "end_line": end,
                "kind": h.kind,
                "num": h.num,
                "title": h.title,
                "preview": preview,
            }
        )
    return out


def main() -> int:
    if not TEXT_PATH.exists():
        raise SystemExit(f"Missing extracted text: {TEXT_PATH}")

    lines = TEXT_PATH.read_text(encoding="utf-8").splitlines()
    headings = extract_headings(lines)
    blocks = build_blocks(lines, headings)
    keyword_hits = extract_keyword_hits(lines)

    out_dir = STEP3_DIR / "Data"
    out_dir.mkdir(parents=True, exist_ok=True)

    out = {
        "source": str(TEXT_PATH),
        "line_count": len(lines),
        "heading_count": len(headings),
        "headings": [h.__dict__ for h in headings],
        "blocks": blocks,
        "keyword_hits": keyword_hits,
        "keywords": _KEYWORDS,
    }

    out_path = out_dir / "step3_index.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
