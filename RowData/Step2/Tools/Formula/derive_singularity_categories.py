from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT_FALLBACK = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FALLBACK) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FALLBACK))

from Step2.Tools.path_utils import find_repo_root


REPO_ROOT = find_repo_root(Path(__file__))
FORMULA_BASE = REPO_ROOT / "Step2" / "Formula" / "7、诊断报告完整流程"
DEFAULT_PDF_PATH = FORMULA_BASE / "1、道易天枢诊断系统之诊断指标体系.pdf"

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


def page_column_text(page: fitz.Page, fallback_x0: float | None = None) -> tuple[str, float | None]:
    words = page.get_text("words")
    if not words:
        return "", None

    header_candidates = [w for w in words if w[4] in {"对应", "奇点"}]
    if not header_candidates:
        if fallback_x0 is None:
            return "", None
        header_candidates = []

    y_limit = page.rect.height * 0.25
    header_candidates = [w for w in header_candidates if w[1] <= y_limit]
    if not header_candidates and fallback_x0 is None:
        return "", None

    best_x0: float | None = None
    best_score = 1e9
    for w in header_candidates:
        if w[4] != "对应":
            continue
        x0, y0 = float(w[0]), float(w[1])
        for u in header_candidates:
            if u[4] != "奇点":
                continue
            ux0, uy0 = float(u[0]), float(u[1])
            if abs(uy0 - y0) > 30:
                continue
            score = abs(ux0 - x0) + abs(uy0 - y0) * 2
            if score < best_score:
                best_score = score
                best_x0 = min(x0, ux0)

    if best_x0 is None:
        if fallback_x0 is None:
            return "", None
        best_x0 = float(fallback_x0)

    col_left = best_x0 - 10
    col_right = best_x0 + 22

    if header_candidates:
        near_col = [w for w in header_candidates if col_left <= float(w[0]) <= col_right]
        header_bottom = (
            max(float(w[3]) for w in near_col)
            if near_col
            else max(float(w[3]) for w in header_candidates)
        ) + 2
    else:
        header_bottom = 0.0

    picked = [w for w in words if (col_left <= float(w[0]) <= col_right) and float(w[1]) > header_bottom]
    if not picked:
        return "", best_x0

    picked.sort(key=lambda t: (t[1], t[0]))
    return "".join(str(w[4]) for w in picked), best_x0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Count singularity label distribution from the PDF's '对应奇点' column")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF_PATH, help=f"Input PDF (default: {DEFAULT_PDF_PATH})")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    pdf_path: Path = args.pdf
    if not pdf_path.exists():
        raise SystemExit(f"Missing PDF: {pdf_path}")

    doc = fitz.open(pdf_path)
    tokens: list[str] = []
    last_x0: float | None = None
    for i in range(doc.page_count):
        page = doc.load_page(i)
        col_text, used_x0 = page_column_text(page, fallback_x0=last_x0)
        if used_x0 is not None:
            last_x0 = used_x0
        if not col_text:
            continue
        tokens.extend(SING_RE.findall(col_text))
    doc.close()

    c = Counter(tokens)
    print(f"source={pdf_path}")
    print(f"matched={len(tokens)} unique={len(c)}")
    for name, count in c.most_common():
        print(f"{count:>4}  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
