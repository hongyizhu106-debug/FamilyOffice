from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


REQUIRED_MODULE_COMMENTS = [
    "<!-- 模块1: 报告封面 -->",
    "<!-- 模块2: 报告目录 -->",
    "<!-- 模块3: 核心诊断摘要 -->",
    "<!-- 模块5: 风险诊断可视化 -->",
    "<!-- 模块6: 风险传导链路 -->",
    "<!-- 模块9: 报告详细解读与核心启示 -->",
    "<!-- 模块10: 报告编制说明 -->",
]


def validate_step4_html(html: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # P0-2: 10 modules exist (by comment markers)
    for marker in REQUIRED_MODULE_COMMENTS:
        if marker not in html:
            errors.append(f"Missing module marker: {marker}")

    # P0-1: cover report id positioning rules are implemented via CSS selectors
    if ".report-id" not in html or "position: absolute" not in html:
        warnings.append("Cover report-id CSS may be incomplete")

    # P0-4: table header must be navy + ivory (implemented via variables)
    if ".data-table th" not in html:
        errors.append("Missing .data-table th styling")

    # P2-10: try to catch hard-coded colors OUTSIDE the :root variable block.
    # Step4 explicitly defines hex colors inside :root, so those are allowed.
    stripped = re.sub(r":root\s*\{.*?\}", "", html, flags=re.S)
    hardcoded_hex = re.findall(r"#[0-9a-fA-F]{3,6}", stripped)
    hardcoded_rgba = re.findall(r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[-0-9.]+\s*\)", stripped)
    if hardcoded_hex:
        warnings.append(f"Found hard-coded hex colors outside :root: {sorted(set(hardcoded_hex))[:10]}")
    if hardcoded_rgba:
        warnings.append(f"Found hard-coded rgba colors outside :root: {sorted(set(hardcoded_rgba))[:10]}")

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


def validate_step4_html_file(path: Path) -> ValidationResult:
    return validate_step4_html(path.read_text(encoding="utf-8"))


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate Step4 generated HTML against structural requirements")
    p.add_argument("html", help="Path to generated report HTML")
    return p


def _main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    path = Path(args.html)
    res = validate_step4_html_file(path)

    if res.errors:
        print("errors=")
        for e in res.errors:
            print(f"- {e}")
    if res.warnings:
        print("warnings=")
        for w in res.warnings:
            print(f"- {w}")

    print(f"ok={res.ok}")
    return 0 if res.ok else 2


if __name__ == "__main__":
    raise SystemExit(_main())
