from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MAPPING_PATTERN = re.compile(
    r"^\s*(?P<code>[^（(]+?)\s*[（(](?P<name>[^）)]+)[）)]\s*$"
)


def iter_questions(bank: dict[str, Any]):
    for section in bank.get("sections", []):
        for group in section.get("groups", []):
            for question in group.get("questions", []):
                yield question


def normalize_mappings_in_bank(bank: dict[str, Any]) -> dict[str, Any]:
    """Normalize mapping codes for duplicate indicator names.

    Rule: for the same indicator name (text inside parentheses), use the code
    from the first time this name appears in the bank.

    Example: "M1-D1-T1-I1（决策权基尼系数）" wins over later occurrences like
    "M2-D3-T7-I9（决策权基尼系数）".
    """

    name_to_first_code: dict[str, str] = {}
    stats = {
        "total_mappings": 0,
        "parsed_mappings": 0,
        "changed_mappings": 0,
        "names_with_conflicts": 0,
    }

    # Track conflicts for reporting.
    conflicts: dict[str, set[str]] = {}

    for question in iter_questions(bank):
        mappings = question.get("mappings")
        if not isinstance(mappings, list):
            continue

        new_mappings: list[str] = []
        changed_this_question = False

        for m in mappings:
            stats["total_mappings"] += 1
            if not isinstance(m, str):
                new_mappings.append(m)
                continue

            mm = MAPPING_PATTERN.match(m)
            if not mm:
                new_mappings.append(m)
                continue

            stats["parsed_mappings"] += 1
            code = mm.group("code").strip()
            name = mm.group("name").strip()

            if name not in name_to_first_code:
                name_to_first_code[name] = code
                new_mappings.append(f"{code}（{name}）")
                continue

            first_code = name_to_first_code[name]
            if code != first_code:
                conflicts.setdefault(name, set()).update({first_code, code})
                new_mappings.append(f"{first_code}（{name}）")
                stats["changed_mappings"] += 1
                changed_this_question = True
            else:
                new_mappings.append(f"{code}（{name}）")

        if changed_this_question:
            question["mappings"] = new_mappings

    stats["names_with_conflicts"] = len(conflicts)
    bank["_normalize_mappings_stats"] = stats
    if conflicts:
        # Keep a short preview only; full conflict detail can be re-derived.
        bank["_normalize_mappings_conflicts_preview"] = {
            name: sorted(list(codes))[:10] for name, codes in sorted(conflicts.items())[:50]
        }
    return bank


def analyze_bank_mappings(bank: dict[str, Any]) -> dict[str, Any]:
    """Analyze mapping consistency in the bank.

    Returns a dict with counts:
    - total_items: total mapping list items across all questions
    - string_items: how many of those are strings
    - parsed_items: how many strings match the expected "CODE（NAME）" format
    - unparsed_string_items: strings that didn't match the format
    - unique_names: distinct indicator names
    - unique_codes: distinct indicator codes
    - names_with_multiple_codes: count of names mapped to >1 code
    - codes_with_multiple_names: count of codes used by >1 name
    - would_change_items: if we re-apply the "first code wins" rule, how many items would change
    """

    total_items = 0
    string_items = 0
    parsed_items = 0
    unparsed_string_items = 0

    name_to_codes: dict[str, set[str]] = {}
    code_to_names: dict[str, set[str]] = {}
    name_to_first_code: dict[str, str] = {}
    would_change_items = 0

    for question in iter_questions(bank):
        mappings = question.get("mappings")
        if not isinstance(mappings, list):
            continue

        for item in mappings:
            total_items += 1
            if not isinstance(item, str):
                continue

            string_items += 1
            m = MAPPING_PATTERN.match(item)
            if not m:
                unparsed_string_items += 1
                continue

            parsed_items += 1
            code = m.group("code").strip()
            name = m.group("name").strip()
            name_to_codes.setdefault(name, set()).add(code)
            code_to_names.setdefault(code, set()).add(name)

            if name not in name_to_first_code:
                name_to_first_code[name] = code
            else:
                if code != name_to_first_code[name]:
                    would_change_items += 1

    names_with_multiple_codes = sum(1 for codes in name_to_codes.values() if len(codes) > 1)
    codes_with_multiple_names = sum(1 for names in code_to_names.values() if len(names) > 1)

    return {
        "total_items": total_items,
        "string_items": string_items,
        "parsed_items": parsed_items,
        "unparsed_string_items": unparsed_string_items,
        "unique_names": len(name_to_codes),
        "unique_codes": len(code_to_names),
        "names_with_multiple_codes": names_with_multiple_codes,
        "codes_with_multiple_names": codes_with_multiple_names,
        "would_change_items": would_change_items,
        "code_to_names": {c: sorted(list(ns)) for c, ns in code_to_names.items() if len(ns) > 1},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize mapping codes for duplicate indicator names in Question_bank.json"
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "Data" / "Question_bank.json",
        help="Input bank JSON path (default: Data/Question_bank.json)",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        type=Path,
        default=None,
        help="Output path (default: overwrite input)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Only report current mapping stats; do not write any files",
    )
    parser.add_argument(
        "--show-code-conflicts",
        type=int,
        default=0,
        metavar="N",
        help="When used with --report, print up to N codes that map to multiple names",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped backup before overwriting",
    )
    args = parser.parse_args()

    in_path: Path = args.in_path
    out_path: Path = args.out_path or in_path

    bank = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(bank, dict):
        raise SystemExit("Invalid bank JSON (expected object)")

    if args.report:
        report = analyze_bank_mappings(bank)
        print(f"Bank: {in_path}")
        print(
            "mappings:",
            "total=", report["total_items"],
            "strings=", report["string_items"],
            "parsed=", report["parsed_items"],
            "unparsed_strings=", report["unparsed_string_items"],
        )
        print(
            "unique:",
            "names=", report["unique_names"],
            "codes=", report["unique_codes"],
            "names>1code=", report["names_with_multiple_codes"],
            "codes>1name=", report["codes_with_multiple_names"],
        )
        print("reapply_rule_would_change_items=", report["would_change_items"])

        n = int(args.show_code_conflicts or 0)
        if n > 0:
            conflicts = report.get("code_to_names", {})
            items = sorted(conflicts.items(), key=lambda x: (-len(x[1]), x[0]))
            print(f"code->multiple-names (showing {min(n, len(items))}/{len(items)}):")
            for code, names in items[:n]:
                print(f"  {code} => {names}")
        return 0

    updated = normalize_mappings_in_bank(bank)

    if out_path == in_path and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = in_path.with_name(f"{in_path.stem}.bak_{ts}{in_path.suffix}")
        backup_path.write_text(in_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup: {backup_path}")

    out_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    stats = updated.get("_normalize_mappings_stats", {})
    print(
        "Done. total=", stats.get("total_mappings"),
        "parsed=", stats.get("parsed_mappings"),
        "changed=", stats.get("changed_mappings"),
        "conflict_names=", stats.get("names_with_conflicts"),
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
