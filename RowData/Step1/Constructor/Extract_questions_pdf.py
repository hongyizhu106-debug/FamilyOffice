from __future__ import annotations

import argparse
from pathlib import Path

import fitz  # PyMuPDF


def extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    try:
        parts: list[str] = []
        for page in doc:
            text = page.get_text("text")
            parts.append(text)
        return "\n".join(parts)
    finally:
        doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract plain text from a PDF.")
    parser.add_argument("pdf", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output text file path (default: <pdf>.txt)",
    )
    args = parser.parse_args()

    pdf_path: Path = args.pdf
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    out_path = args.out or pdf_path.with_suffix(".txt")

    text = extract_text(pdf_path)
    out_path.write_text(text, encoding="utf-8")
    print(f"Extracted text written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
