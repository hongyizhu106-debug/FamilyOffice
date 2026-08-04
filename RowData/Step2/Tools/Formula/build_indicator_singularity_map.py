from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable

import fitz  # PyMuPDF

# Make repo root importable when running this file directly.
REPO_ROOT_FALLBACK = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FALLBACK) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FALLBACK))

from Step2.Tools.path_utils import find_repo_root


REPO_ROOT = find_repo_root(Path(__file__))
FORMULA_BASE = REPO_ROOT / "Step2" / "Formula" / "7、诊断报告完整流程"
DEFAULT_PDF_PATH = FORMULA_BASE / "1、道易天枢诊断系统之诊断指标体系.pdf"
DEFAULT_OUT_PATH = REPO_ROOT / "Step2" / "Data" / "indicator_singularity_map.json"

EXPECTED = [
    "人物奇点",
    "财务奇点",
    "事件奇点",
    "技术奇点",
    "时间奇点",
    "权力/决策奇点",
    "认知/文化奇点",
]
SING_RE = re.compile("|".join(map(re.escape, EXPECTED)))
CODE_RE = re.compile(r"M\d+-D\d+-T\d+-I\d+")
CODE_PREFIX_RE = re.compile(r"^M\d+-D\d+-$")
CODE_TAIL_RE = re.compile(r"^T\d+-I\d+$")

SING_TOKEN_RE = re.compile(r"^(权力/|认知/|决策|文化|人物|财务|事件|技术|时间|奇点)$")


@dataclass(frozen=True)
class ColSpec:
    left: float
    right: float
    header_bottom: float


def _norm_text(s: str) -> str:
    s = s.replace("－", "-").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", "", s)


def _find_header_word(words: list[tuple], text: str) -> tuple | None:
    for w in words:
        if w[4] == text:
            return w
    return None


def _detect_code_x0(words: list[tuple]) -> float | None:
    xs: list[float] = []
    for w in words:
        t = _norm_text(str(w[4]))
        if not t:
            continue
        if CODE_PREFIX_RE.match(t) or CODE_TAIL_RE.match(t) or CODE_RE.search(t):
            xs.append(float(w[0]))
    if not xs:
        return None
    return float(median(xs))


def _detect_sing_x0(words: list[tuple]) -> float | None:
    xs: list[float] = []
    for w in words:
        t = _norm_text(str(w[4]))
        if t != "奇点":
            continue
        if float(w[1]) < 120:
            continue
        xs.append(float(w[0]))
    if not xs:
        return None
    return float(median(xs))


def _column_specs(
    page: fitz.Page,
    *,
    fallback_code_x0: float | None = None,
    fallback_sing_x0: float | None = None,
) -> tuple[ColSpec | None, ColSpec | None, float | None, float | None]:
    words = page.get_text("words")
    if not words:
        return None, None, None, None

    code_hdr = _find_header_word(words, "指标编码")
    sing_hdr = _find_header_word(words, "对应")
    tool_hdr = _find_header_word(words, "对应工具/策略")

    used_code_x0 = float(code_hdr[0]) if code_hdr else None
    used_sing_x0 = float(sing_hdr[0]) if sing_hdr else None

    if used_code_x0 is None:
        used_code_x0 = _detect_code_x0(words)
    if used_sing_x0 is None:
        used_sing_x0 = _detect_sing_x0(words)

    if used_code_x0 is None and fallback_code_x0 is not None:
        used_code_x0 = float(fallback_code_x0)
    if used_sing_x0 is None and fallback_sing_x0 is not None:
        used_sing_x0 = float(fallback_sing_x0)

    if used_code_x0 is None or used_sing_x0 is None:
        return None, None, None, None

    if code_hdr and sing_hdr and tool_hdr:
        header_bottom = max(float(code_hdr[3]), float(sing_hdr[3]), float(tool_hdr[3])) + 2.0
    else:
        header_bottom = 0.0

    code_x0 = used_code_x0
    code_col = ColSpec(left=code_x0 - 25.0, right=code_x0 + 95.0, header_bottom=header_bottom)

    sing_x0 = used_sing_x0
    sing_col = ColSpec(left=sing_x0 - 22.0, right=sing_x0 + 140.0, header_bottom=header_bottom)

    return code_col, sing_col, used_code_x0, used_sing_x0


def _pick_words(words: list[tuple], col: ColSpec) -> list[tuple]:
    picked = [
        w
        for w in words
        if col.left <= float(w[0]) <= col.right and float(w[1]) > col.header_bottom
    ]
    picked.sort(key=lambda t: (t[1], t[0]))
    return picked


def _extract_singularity_rows(picked: list[tuple]) -> list[tuple[float, str | None]]:
    tokens: list[tuple[float, float, str]] = []
    for w in picked:
        t = _norm_text(str(w[4]))
        if not t:
            continue
        if SING_TOKEN_RE.match(t):
            tokens.append((float(w[1]), float(w[0]), t))

    tokens.sort(key=lambda t: (t[0], t[1]))

    rows: list[tuple[float, str | None]] = []
    buf: list[str] = []
    row_y: float | None = None

    for y, x, t in tokens:
        buf.append(t)
        row_y = y
        if t != "奇点":
            continue

        text = "".join(buf)
        m = SING_RE.search(text)
        label = m.group(0) if m else None

        if label is not None:
            rows.append((row_y, label))
        buf = []
        row_y = None

    return rows


def _extract_code_rows(picked: list[tuple]) -> list[tuple[float, str]]:
    tokens: list[tuple[float, float, str]] = []
    for w in picked:
        t = _norm_text(str(w[4]))
        if not t:
            continue
        if CODE_PREFIX_RE.match(t) or CODE_TAIL_RE.match(t) or CODE_RE.search(t):
            tokens.append((float(w[1]), float(w[0]), t))

    tokens.sort(key=lambda t: (t[0], t[1]))

    rows: list[tuple[float, str]] = []
    pending_prefix: tuple[str, float] | None = None

    for y, x, t in tokens:
        m = CODE_RE.search(t)
        if m:
            rows.append((y, m.group(0)))
            pending_prefix = None
            continue

        if CODE_PREFIX_RE.match(t):
            pending_prefix = (t, y)
            continue

        if CODE_TAIL_RE.match(t):
            if pending_prefix is None:
                continue
            prefix, py = pending_prefix
            if 0 <= (y - py) <= 40:
                rows.append((y, prefix + t))
                pending_prefix = None
            continue

    return rows


def extract_page_with_fallback(
    page: fitz.Page,
    *,
    fallback_code_x0: float | None,
    fallback_sing_x0: float | None,
) -> tuple[list[str], list[str], float | None, float | None]:
    code_col, sing_col, used_code_x0, used_sing_x0 = _column_specs(
        page,
        fallback_code_x0=fallback_code_x0,
        fallback_sing_x0=fallback_sing_x0,
    )
    if not code_col or not sing_col:
        return [], [], used_code_x0, used_sing_x0

    words = page.get_text("words")
    code_picked = _pick_words(words, code_col)
    sing_picked = _pick_words(words, sing_col)

    code_rows = _extract_code_rows(code_picked)
    sing_rows = _extract_singularity_rows(sing_picked)

    sing_rows.sort(key=lambda t: t[0])

    paired: list[tuple[str, str]] = []
    j = 0
    for cy, code in code_rows:
        while j < len(sing_rows) and sing_rows[j][0] < cy - 30:
            j += 1

        candidates: list[tuple[float, str]] = []
        if j < len(sing_rows) and sing_rows[j][1] is not None:
            candidates.append((abs(sing_rows[j][0] - cy), sing_rows[j][1]))
        if j - 1 >= 0 and sing_rows[j - 1][1] is not None:
            candidates.append((abs(sing_rows[j - 1][0] - cy), sing_rows[j - 1][1]))

        if not candidates:
            continue
        dist, label = min(candidates, key=lambda t: t[0])
        if dist <= 30:
            paired.append((code, label))

    codes = [c for c, _ in paired]
    sings = [s for _, s in paired]
    return codes, sings, used_code_x0, used_sing_x0


def build_map(pdf_path: Path, out_path: Path) -> dict:
    doc = fitz.open(pdf_path)
    code_to_sing: dict[str, str] = {}

    last_code_x0: float | None = None
    last_sing_x0: float | None = None

    mismatch_pages: list[dict[str, int]] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        codes, sings, used_code_x0, used_sing_x0 = extract_page_with_fallback(
            page,
            fallback_code_x0=last_code_x0,
            fallback_sing_x0=last_sing_x0,
        )
        if used_code_x0 is not None:
            last_code_x0 = used_code_x0
        if used_sing_x0 is not None:
            last_sing_x0 = used_sing_x0
        if not codes and not sings:
            continue
        if len(codes) != len(sings):
            mismatch_pages.append({"page": i + 1, "codes": len(codes), "singularities": len(sings)})
        for code, sing in zip(codes, sings):
            code_to_sing.setdefault(code, sing)

    doc.close()

    totals = Counter(code_to_sing.values())
    missing = [s for s in EXPECTED if s not in totals]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pdf": str(pdf_path),
        "expected_singularities": EXPECTED,
        "indicator_count": len(code_to_sing),
        "singularity_indicator_totals": dict(totals),
        "mismatch_pages": mismatch_pages,
        "code_to_singularity": code_to_sing,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote: {out_path}")
    print(f"indicator_count={len(code_to_sing)}")
    print(f"singularity_totals={dict(totals)}")
    if mismatch_pages:
        print("WARNING: page row count mismatches detected:")
        for item in mismatch_pages[:20]:
            print(item)
    if missing:
        print(f"WARNING: missing singularity labels: {missing}")

    return payload


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build indicator-code -> singularity-category map from the indicator system PDF")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF_PATH, help=f"Input PDF (default: {DEFAULT_PDF_PATH})")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help=f"Output JSON (default: {DEFAULT_OUT_PATH})")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    pdf_path: Path = args.pdf
    out_path: Path = args.out

    if not pdf_path.exists():
        raise SystemExit(f"Missing PDF: {pdf_path}")

    build_map(pdf_path, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
