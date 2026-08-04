from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT_FALLBACK = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FALLBACK) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FALLBACK))

from Step2.Tools.path_utils import find_repo_root


REPO_ROOT = find_repo_root(Path(__file__))
FORMULA_BASE = REPO_ROOT / "Step2" / "Formula" / "7、诊断报告完整流程"
DEFAULT_PDF_PATH = FORMULA_BASE / "1、道易天枢诊断系统之诊断指标体系.pdf"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Inspect header word coordinates in the indicator system PDF")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF_PATH, help=f"Input PDF (default: {DEFAULT_PDF_PATH})")
    p.add_argument("--page", type=int, default=1, help="1-based page number (default: 1)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    pdf_path: Path = args.pdf
    page_no_1b: int = args.page

    if not pdf_path.exists():
        raise SystemExit(f"Missing PDF: {pdf_path}")

    doc = fitz.open(pdf_path)
    page_index = max(0, min(doc.page_count - 1, page_no_1b - 1))
    page = doc.load_page(page_index)
    words = page.get_text("words")

    target = {
        "指标编码",
        "指标",
        "编码",
        "对应",
        "奇点",
        "对应工具/策略",
        "工具/策略",
        "风险函数f(x)",
        "风险函数",
        "f(x)",
    }
    headers = [w for w in words if w[4] in target]
    headers.sort(key=lambda w: (w[1], w[0]))

    print(f"pdf={pdf_path}")
    print(f"page={page_index + 1} size={page.rect.width:.1f}x{page.rect.height:.1f}")
    print("-- header candidates --")
    for w in headers[:200]:
        x0, y0, x1, y1, text = w[:5]
        print(f"{text:<12} x0={x0:>7.1f} y0={y0:>7.1f} x1={x1:>7.1f} y1={y1:>7.1f}")

    print("-- all '对应' x0 (sample) --")
    ox = sorted({round(w[0], 1) for w in words if w[4] == "对应"})
    print(ox[:60])

    print("-- all '奇点' x0 (sample) --")
    qx = sorted({round(w[0], 1) for w in words if w[4] == "奇点"})
    print(qx[:60])

    print("-- band y in [85, 150] --")
    band = [w for w in words if 85 <= w[1] <= 150]
    band.sort(key=lambda w: (w[1], w[0]))
    for w in band[:220]:
        x0, y0, x1, y1, text = w[:5]
        print(f"{text:<16} x0={x0:>7.1f} y0={y0:>7.1f}")

    doc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
