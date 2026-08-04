from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def extract_pdf_text(pdf_path: Path, *, max_pages: int | None = None) -> str:
    doc = fitz.open(str(pdf_path))
    pages = doc.page_count
    n = pages if max_pages is None else min(max_pages, pages)

    parts: list[str] = []
    for i in range(n):
        page = doc.load_page(i)
        txt = page.get_text("text")
        txt = "\n".join(line.rstrip() for line in txt.splitlines())
        parts.append(f"\n{'='*20} PAGE {i+1}/{pages} {'='*20}\n{txt}\n")

    return "\n".join(parts)


def main() -> int:
    pdf_path = Path(__file__).resolve().parent / "2、道易天枢诊断系统之家族奇点算法体系2.0.pdf"
    if not pdf_path.exists():
        raise SystemExit(f"Missing PDF: {pdf_path}")

    out_dir = Path(__file__).resolve().parent / "_extracted_text"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "step3_text.txt"

    text = extract_pdf_text(pdf_path, max_pages=None)
    out_path.write_text(text, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
