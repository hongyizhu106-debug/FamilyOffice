from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


CODE_RE = re.compile(r"M\d+-D\d+-T\d+-I\d+")


def _find_repo_root(start: Path) -> Path:
    start = start.resolve()
    for parent in [start, *start.parents]:
        if (parent / "README.md").exists() and (parent / "Step1").exists() and (parent / "Step2").exists():
            return parent
    return start


REPO_ROOT = _find_repo_root(Path(__file__))
DEFAULT_MAP = REPO_ROOT / "Step2" / "Data" / "indicator_singularity_map.json"
DEFAULT_BANK = REPO_ROOT / "Step1" / "Data" / "Question_bank.json"
DEFAULT_RUBBISH = REPO_ROOT / "Step1" / "Rubbish"


@dataclass(frozen=True)
class Coverage:
    total_distinct: int
    mapped_distinct: int

    @property
    def rate(self) -> float:
        return (self.mapped_distinct / self.total_distinct) if self.total_distinct else 0.0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_codes_from_bank(bank: dict[str, Any]) -> tuple[set[str], dict[str, list[str]]]:
    """Return (codes, code->question_ids)."""

    codes: set[str] = set()
    refs: dict[str, list[str]] = {}

    for section in bank.get("sections", []) or []:
        for group in section.get("groups", []) or []:
            for q in group.get("questions", []) or []:
                qid = q.get("id")
                qid_str = str(qid) if isinstance(qid, (str, int)) else ""
                for m in q.get("mappings", []) or []:
                    if not isinstance(m, str):
                        continue
                    mm = CODE_RE.search(m)
                    if not mm:
                        continue
                    code = mm.group(0)
                    codes.add(code)
                    if qid_str:
                        refs.setdefault(code, [])
                        if len(refs[code]) < 30:  # keep file size reasonable
                            refs[code].append(qid_str)

    return codes, refs


def _extract_codes_from_code_weights(code_weights: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for k in (code_weights or {}).keys():
        if not isinstance(k, str):
            continue
        mm = CODE_RE.search(k)
        if mm:
            codes.add(mm.group(0))
    return codes


def compute_coverage(*, codes: Iterable[str], code_to_singularity: dict[str, Any]) -> Coverage:
    code_set = {c for c in codes if isinstance(c, str) and c.strip()}
    mapped = {c for c in code_set if isinstance(code_to_singularity.get(c), str)}
    return Coverage(total_distinct=len(code_set), mapped_distinct=len(mapped))


def _latest_response_file(rubbish_dir: Path) -> Path | None:
    if not rubbish_dir.exists():
        return None
    files = sorted(
        rubbish_dir.glob("web_response_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _group_code(code: str) -> str:
    """Group key to help identify which batch a code belongs to."""
    # Mx-Dy-Tz-Iw -> Mx-Dy-Tz
    parts = code.split("-")
    return "-".join(parts[:3]) if len(parts) >= 3 else code


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Report mapping coverage between Step1 questionnaire codes and Step2 singularity map")
    p.add_argument("--map", type=Path, default=DEFAULT_MAP, help="Mapping JSON path (Step2)")
    p.add_argument("--bank", type=Path, default=DEFAULT_BANK, help="Question bank JSON path (Step1)")
    p.add_argument("--response", type=Path, default=None, help="A specific response JSON path (Step1/Rubbish)")
    p.add_argument("--rubbish", type=Path, default=DEFAULT_RUBBISH, help="Rubbish dir to auto-pick latest response")
    p.add_argument(
        "--dump-unmapped",
        type=Path,
        default=None,
        help="Write unmapped bank codes (and references) to a JSON file",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    map_path: Path = args.map
    bank_path: Path = args.bank

    if not map_path.exists():
        raise SystemExit(f"Missing map: {map_path}")
    if not bank_path.exists():
        raise SystemExit(f"Missing question bank: {bank_path}")

    mp = _load_json(map_path)
    code_to_sing = mp.get("code_to_singularity") if isinstance(mp, dict) else None
    if not isinstance(code_to_sing, dict):
        raise SystemExit(f"Invalid map format: {map_path}")

    bank = _load_json(bank_path)
    if not isinstance(bank, dict):
        raise SystemExit(f"Invalid bank format: {bank_path}")

    bank_codes, bank_refs = _extract_codes_from_bank(bank)
    cov = compute_coverage(codes=bank_codes, code_to_singularity=code_to_sing)
    print(f"[bank] distinct_codes={cov.total_distinct} mapped={cov.mapped_distinct} rate={cov.rate:.4f}")

    map_codes = {c for c in code_to_sing.keys() if isinstance(c, str)}
    only_in_bank = sorted(bank_codes - map_codes)
    only_in_map = sorted(map_codes - bank_codes)
    print(f"[diff] only_in_bank={len(only_in_bank)} only_in_map={len(only_in_map)}")

    if args.dump_unmapped is not None:
        groups: dict[str, list[str]] = {}
        for c in only_in_bank:
            groups.setdefault(_group_code(c), []).append(c)

        payload = {
            "generated_at": "",
            "bank_path": str(bank_path),
            "map_path": str(map_path),
            "only_in_bank_count": len(only_in_bank),
            "only_in_map_count": len(only_in_map),
            "groups": {k: v for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
            "unmapped": [
                {
                    "code": c,
                    "group": _group_code(c),
                    "question_ids": bank_refs.get(c, []),
                }
                for c in only_in_bank
            ],
        }
        args.dump_unmapped.parent.mkdir(parents=True, exist_ok=True)
        args.dump_unmapped.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[dump] wrote={args.dump_unmapped}")

    response_path: Path | None = args.response
    if response_path is None:
        response_path = _latest_response_file(args.rubbish)

    if response_path and response_path.exists():
        resp = _load_json(response_path)
        cw = resp.get("code_weights") if isinstance(resp, dict) else None
        if isinstance(cw, dict):
            resp_codes = _extract_codes_from_code_weights(cw)
            rcov = compute_coverage(codes=resp_codes, code_to_singularity=code_to_sing)
            print(
                f"[response] file={response_path} distinct_codes={rcov.total_distinct} mapped={rcov.mapped_distinct} rate={rcov.rate:.4f}"
            )

            resp_unmapped = sorted(resp_codes - map_codes)
            if resp_unmapped:
                print(f"[response] unmapped_distinct={len(resp_unmapped)}")
        else:
            print(f"[response] file={response_path} has no code_weights")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
