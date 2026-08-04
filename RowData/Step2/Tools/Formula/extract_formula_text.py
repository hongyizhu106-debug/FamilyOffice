from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import fitz  # PyMuPDF

REPO_ROOT_FALLBACK = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FALLBACK) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FALLBACK))

from Step2.Tools.path_utils import find_repo_root


REPO_ROOT = find_repo_root(Path(__file__))
FORMULA_BASE = REPO_ROOT / "Step2" / "Formula" / "7、诊断报告完整流程"
DEFAULT_OUT_DIR = FORMULA_BASE / "_extracted_text"

DEFAULT_PDFS = [
    FORMULA_BASE / "1、道易天枢诊断系统之诊断指标体系.pdf",
    FORMULA_BASE / "3、家族传承诊断报告标准化输出规范.pdf",
]
DEFAULT_DOCXS = [
    FORMULA_BASE / "4、家族传承诊断报告HTML转换专业提示词系统.docx",
    FORMULA_BASE / "诊断报告的要求.docx",
]


def clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(path)
    parts: list[str] = []

    for i in range(doc.page_count):
        page = doc.load_page(i)
        parts.append(f"\n\n===== Page {i + 1} =====\n")

        blocks = page.get_text("blocks")
        text_blocks: list[tuple[float, float, str]] = []
        for b in blocks:
            if len(b) < 7:
                continue
            x0, y0, _, _, text, _, block_type = b
            if block_type != 0:
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            text_blocks.append((float(y0), float(x0), text))

        if text_blocks:
            text_blocks.sort(key=lambda t: (round(t[0], 1), t[1]))
            parts.append("\n".join(t[2].rstrip() for t in text_blocks))
        else:
            parts.append(page.get_text("text"))

    doc.close()
    return clean_text("".join(parts))


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml_bytes = z.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    paras: list[str] = []
    for p in root.findall(".//w:p", ns):
        texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
        if texts:
            paras.append("".join(texts))

    raw = "\n".join(paras)
    raw = re.sub(r"[ \t\u3000]+", " ", raw)
    return clean_text(raw)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract text from Formula PDFs/DOCXs into plain .txt for inspection")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help=f"Output directory (default: {DEFAULT_OUT_DIR})")
    p.add_argument("--pdf", type=Path, action="append", default=None, help="PDF path (repeatable)")
    p.add_argument("--docx", type=Path, action="append", default=None, help="DOCX path (repeatable)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = args.pdf if args.pdf else DEFAULT_PDFS
    docxs = args.docx if args.docx else DEFAULT_DOCXS

    missing = False

    for p in pdfs:
        if not p.exists():
            print("Missing PDF:", p)
            missing = True
            continue
        out = out_dir / (p.stem + ".txt")
        out.write_text(extract_pdf_text(p), encoding="utf-8")
        print("PDF ->", out)

    for d in docxs:
        if not d.exists():
            print("Missing DOCX:", d)
            missing = True
            continue
        out = out_dir / (d.stem + ".txt")
        out.write_text(extract_docx_text(d), encoding="utf-8")
        print("DOCX ->", out)

    print("Done. Output:", out_dir)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
