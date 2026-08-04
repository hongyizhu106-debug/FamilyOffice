from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_bank(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_html(bank: dict[str, Any]) -> str:
    title = str(bank.get("title") or "问卷")

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append("<html lang=\"zh\">")
    parts.append("<head>")
    parts.append("  <meta charset=\"utf-8\" />")
    parts.append(f"  <title>{_html_escape(title)} - 题库预览</title>")
    parts.append(
        "  <style>\n"
        "    :root { color-scheme: only light; }\n"
        "    body { font-family: \"Segoe UI\", \"Microsoft YaHei\", sans-serif; margin: 24px; color: #1f2328; }\n"
        "    h1 { font-size: 24px; margin: 0 0 16px; }\n"
        "    h2 { font-size: 18px; margin: 24px 0 8px; }\n"
        "    h3 { font-size: 16px; margin: 16px 0 6px; }\n"
        "    .meta { color: #57606a; font-size: 12px; margin-bottom: 18px; }\n"
        "    .question { margin: 10px 0 14px; padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 8px; }\n"
        "    .q-title { font-weight: 600; margin-bottom: 8px; }\n"
        "    .options { margin: 0; padding-left: 18px; }\n"
        "    .options li { margin: 2px 0; }\n"
        "    .mappings { color: #6b7280; font-size: 12px; margin-top: 6px; }\n"
        "    .page-break { page-break-after: always; }\n"
        "  </style>"
    )
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"  <h1>{_html_escape(title)} - 题库预览</h1>")

    sections = bank.get("sections") if isinstance(bank, dict) else []
    section_count = len(sections) if isinstance(sections, list) else 0
    parts.append(f"  <div class=\"meta\">模块数：{section_count}</div>")

    for section in sections or []:
        sec_title = _html_escape(str(section.get("title") or "未分模块"))
        parts.append(f"  <h2>{sec_title}</h2>")
        for group in section.get("groups", []) or []:
            grp_title = _html_escape(str(group.get("title") or "未分问题组"))
            parts.append(f"  <h3>{grp_title}</h3>")
            for q in group.get("questions", []) or []:
                q_number = _html_escape(str(q.get("number") or ""))
                q_text = _html_escape(str(q.get("text") or ""))
                q_id = _html_escape(str(q.get("id") or ""))

                parts.append("  <div class=\"question\">")
                parts.append(f"    <div class=\"q-title\">{q_number}. {q_text}</div>")
                if q_id:
                    parts.append(f"    <div class=\"mappings\">ID: {q_id}</div>")

                parts.append("    <ol class=\"options\">")
                for opt in q.get("options", []) or []:
                    key = _html_escape(str(opt.get("key") or ""))
                    label = _html_escape(str(opt.get("label") or ""))
                    parts.append(f"      <li><strong>{key}</strong>. {label}</li>")
                parts.append("    </ol>")

                mappings = q.get("mappings")
                if isinstance(mappings, list) and mappings:
                    joined = _html_escape("; ".join(str(m) for m in mappings if m))
                    parts.append(f"    <div class=\"mappings\">映射指标：{joined}</div>")

                parts.append("  </div>")

    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _try_export_pdf(html_path: Path, pdf_path: Path) -> tuple[bool, str | None]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - best effort
        return False, f"playwright not available: {exc}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            browser.close()
        return True, None
    except Exception as exc:  # pragma: no cover - best effort
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export question bank to HTML/PDF.")
    parser.add_argument(
        "--bank",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "Data" / "Question_bank.json",
        help="Question bank JSON path.",
    )
    parser.add_argument(
        "--out-html",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "Question_bank_preview.html",
        help="Output HTML path.",
    )
    parser.add_argument(
        "--out-pdf",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "Question_bank_preview.pdf",
        help="Output PDF path.",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF export (HTML only).",
    )
    args = parser.parse_args()

    bank = _load_bank(args.bank)
    html = _build_html(bank)
    args.out_html.write_text(html, encoding="utf-8")
    print(f"html={args.out_html}")

    if args.no_pdf:
        return 0

    ok, err = _try_export_pdf(args.out_html, args.out_pdf)
    if ok:
        print(f"pdf={args.out_pdf}")
        return 0

    print(f"pdf=SKIPPED ({err})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
